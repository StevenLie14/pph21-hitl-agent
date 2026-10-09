from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EMBED_DIR = Path(os.environ.get("PPH21_DATA") or "data") / "embedding"


def fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _neo4j_env() -> None:
    for f in (ROOT / ".env", ROOT.parent / ".env"):
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                k, _, v = line.strip().partition("=")
                if k.startswith("NEO4J_") and v and k not in os.environ:
                    os.environ[k] = v.strip().strip('"').strip("'")


def _driver():
    from neo4j import GraphDatabase

    _neo4j_env()
    uri, password = os.getenv("NEO4J_V2_URI"), os.getenv("NEO4J_V2_PASSWORD")
    if not uri or not password:
        raise SystemExit("NEO4J_V2_URI dan NEO4J_V2_PASSWORD wajib diset")
    d = GraphDatabase.driver(uri, auth=(os.getenv("NEO4J_V2_USER", "neo4j"), password))
    d.verify_connectivity()
    return d


MODELS = {
    "gemini": {"api": "gemini", "id": "gemini-embedding-2", "dim": 3072, "batch": 100,
               "query": "task: search result | query: ", "doc": "title: none | text: "},
}
API_KEYS = {"gemini": "GOOGLE_API_KEY"}
MAX_CHARS = 20000


def _folder(name: str) -> Path:
    return EMBED_DIR / name


def _api_key(api: str) -> str:
    name = API_KEYS[api]
    if not os.getenv(name):
        for f in (ROOT / ".env", ROOT.parent / ".env"):
            if f.exists():
                for b in f.read_text(encoding="utf-8").splitlines():
                    k, _, v = b.strip().partition("=")
                    if k == name and v.strip().strip('"').strip("'"):
                        os.environ[name] = v.strip().strip('"').strip("'")
                        break
    if not os.getenv(name):
        raise SystemExit(f"{name} belum diisi di .env")
    return os.environ[name]


def _nodes(label: str = "Chunk") -> list[dict]:
    q = {"Chunk": "MATCH (n:Chunk) WHERE n.search_text IS NOT NULL RETURN n.id AS id, n.search_text AS teks",
         "FAQ": "MATCH (n:FAQ) RETURN n.id AS id, n.question + '\\n' + n.answer AS teks"}[label]
    d = _driver()
    try:
        with d.session() as s:
            return [r.data() for r in s.run(q + " ORDER BY n.id") if r["teks"]]
    finally:
        d.close()


def _cache(f: Path) -> dict[str, np.ndarray]:
    result = {}
    for x in sorted(f.glob("padat_*.npz")):
        z = np.load(x)
        result.update(zip(z["h"].tolist(), z["d"]))
    return result


def _post(url: str, body: dict, headers: dict) -> dict:
    import requests

    for attempt in range(8):
        try:
            r = requests.post(url, json=body, headers=headers, timeout=120)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(60, 2 ** attempt))
            continue
        raise SystemExit(f"API galat {r.status_code}: {r.text[:300]}")
    raise SystemExit("API gagal sesudah 8 percobaan")


def _normalize(v: np.ndarray) -> np.ndarray:
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def _encoder(name: str) -> Callable[[list[str], str], np.ndarray]:
    m = MODELS[name]
    if m.get("api") == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m['id']}:batchEmbedContents"
        headers = {"x-goog-api-key": _api_key("gemini")}

        def encode_gemini(texts: list[str], side: str) -> np.ndarray:
            body = {"requests": [{"model": f"models/{m['id']}", "outputDimensionality": m["dim"],
                                  "content": {"parts": [{"text": (m[side] + t)[:MAX_CHARS]}]}} for t in texts]}
            return _normalize(np.array([e["values"] for e in _post(url, body, headers)["embeddings"]],
                                       dtype=np.float32))
        return encode_gemini

    raise SystemExit(f"model tidak dikenal: {name}")


def compute(name: str, a) -> None:
    f = _folder(name)
    f.mkdir(parents=True, exist_ok=True)
    nodes = _nodes() + (_nodes("FAQ") if a.faq else [])
    cached = _cache(f)
    texts = {fingerprint(x["teks"]): x["teks"] for x in nodes}
    pending = sorted((h for h in texts if h not in cached), key=lambda h: -len(texts[h]))
    chars = sum(len(texts[h]) for h in pending)
    print(f"{len(nodes)} potongan, teks unik {len(texts)}, di cache {len(texts) - len(pending)}, perlu {len(pending)} "
          f"(~{chars / 3.2 / 1e6:.1f} juta token)", flush=True)
    (f / "meta.json").write_text(json.dumps(MODELS[name], ensure_ascii=False, indent=1), encoding="utf-8")
    if not pending:
        return
    encode = _encoder(name)
    batch = MODELS[name].get("batch", 256)
    number, t0, done = len(list(f.glob("padat_*.npz"))), time.time(), 0
    for i in range(0, len(pending), a.shard):
        hs = pending[i:i + a.shard]
        parts = [hs[j:j + batch] for j in range(0, len(hs), batch)]
        with ThreadPoolExecutor(a.parallel) as ex:
            v = np.concatenate(list(ex.map(lambda b: encode([texts[h] for h in b], "doc"), parts)))
        np.savez(f / f"padat_{number:04d}.npz", h=np.array(hs), d=v.astype(np.float16))
        number += 1
        done += len(hs)
        rate = (time.time() - t0) / done
        print(f"{done}/{len(pending)} {rate * 1000:.0f} ms/teks, sisa ~{(len(pending) - done) * rate / 60:.0f} menit",
              flush=True)
    print(f"SELESAI {done} teks dalam {(time.time() - t0) / 60:.1f} menit", flush=True)


VECTOR_INDEXES = {"Chunk": "chunk_vector_gemini", "FAQ": "faq_vector_gemini"}


def write(name: str, a) -> None:
    if name != "gemini":
        raise SystemExit("write hanya untuk gemini (model yang dipakai agent)")
    cached = _cache(_folder(name))
    d = _driver()
    try:
        with d.session() as s:
            for label, index in VECTOR_INDEXES.items():
                if label not in a.labels:
                    continue
                xs = [x for x in _nodes(label) if fingerprint(x["teks"]) in cached]
                for i in range(0, len(xs), a.batch):
                    part = xs[i:i + a.batch]
                    v = _normalize(np.stack([cached[fingerprint(x["teks"])][:a.dim] for x in part]).astype(np.float32))
                    s.run(f"UNWIND $b AS b MATCH (n:{label} {{id: b.id}}) "
                          "CALL db.create.setNodeVectorProperty(n, 'embedding_gemini', b.v)",
                          b=[{"id": x["id"], "v": [round(float(z), 6) for z in r]}
                             for x, r in zip(part, v, strict=True)]).consume()
                    print(f"{label} {min(i + a.batch, len(xs))}/{len(xs)}", flush=True)
                s.run(f"CREATE VECTOR INDEX {index} IF NOT EXISTS FOR (n:{label}) ON n.embedding_gemini OPTIONS "
                      f"{{indexConfig: {{`vector.dimensions`: {a.dim}, `vector.similarity_function`: 'cosine'}}}}"
                      ).consume()
                print(f"{label}: {len(xs)} vektor {a.dim} dimensi ditulis; indeks {index}", flush=True)
            s.run("CALL db.awaitIndexes(1800)").consume()
    finally:
        d.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Gemini embedding vectors for the graph chunks and FAQ nodes (used by the agent's ``search_text``/``search_faq``).")
    ap.add_argument("model", choices=sorted(MODELS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("compute")
    h.add_argument("--shard", dest="shard", type=int, default=1024,
                   help="teks per berkas cache (titik lanjut bila terhenti)")
    h.add_argument("--parallel", dest="parallel", type=int, default=4, help="permintaan API bersamaan")
    h.add_argument("--faq", action="store_true", help="ikut embed node FAQ (untuk search_faq agent)")
    h.set_defaults(func=compute)
    t = sub.add_parser("write")
    t.add_argument("--dim", type=int, default=768, help="dimensi yang ditulis (MRL), sama dengan PPH21_GEMINI_DIM")
    t.add_argument("--batch", type=int, default=250)
    t.add_argument("--labels", nargs="+", choices=sorted(VECTOR_INDEXES), default=sorted(VECTOR_INDEXES),
                   help="label yang ditulis (mis. hanya FAQ setelah node FAQ ditulis ulang)")
    t.set_defaults(func=write)
    a = ap.parse_args()
    a.func(a.model, a)


if __name__ == "__main__":
    main()
