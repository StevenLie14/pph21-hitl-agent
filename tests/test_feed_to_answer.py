from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

from taxagent.corpus.text_source import CorpusIndex, jdih_first
from taxagent.evaluation import agent_backtest as A
from taxagent.update.backtest import documents, load_events, load_labels
from taxagent.update.llm import LLMResult, combine_llm

LONG = "x" * 1200


def _index(tmp_path, rows):
    for r in rows:
        p = tmp_path / f"{r['id']}.txt"
        p.write_text(r.pop("isi"), encoding="utf-8")
        r["teks"] = str(p)
    idx = tmp_path / "indeks.jsonl"
    idx.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return CorpusIndex(idx)


def test_text_source_prefers_reliable_jdih_then_pajak_then_doubtful_jdih(tmp_path):
    c = _index(tmp_path, [
        {"sumber": "jdih", "id": "j1", "kunci": "PMK 168 Tahun 2023", "mutu": "andal", "isi": "J" + LONG},
        {"sumber": "pajak", "id": "p1", "kunci": "PMK 168 Tahun 2023", "mutu": "andal", "isi": "P" + LONG},
        {"sumber": "jdih", "id": "j2", "kunci": "PP 58 Tahun 2023", "mutu": "perlu_dicek", "isi": "D" + LONG},
        {"sumber": "pajak", "id": "p2", "kunci": "PP 58 Tahun 2023", "mutu": "andal", "isi": "Q" + LONG},
        {"sumber": "jdih", "id": "j3", "kunci": "PMK 101 Tahun 2016", "mutu": "perlu_dicek", "isi": "E" + LONG},
    ])
    a = c.pick("PMK No. 168 Tahun 2023")
    assert (a.source, a.jdih_id, a.text[0]) == ("jdih", "j1", "J")
    assert c.pick("PP 58 Tahun 2023").text[0] == "Q"
    b = c.pick("PMK 101 Tahun 2016")
    assert b.text[0] == "E" and b.label == "jdih (perlu_dicek)"
    assert c.pick("PMK 101 Tahun 2016", "S" + LONG).text[0] == "S"
    text, source = jdih_first(["PMK 168 Tahun 2023", "UU 7 Tahun 2021"], {"UU 7 Tahun 2021": "pendek"}, c)
    assert source == {"PMK 168 Tahun 2023": "jdih", "UU 7 Tahun 2021": "pajak.go.id"}
    assert text["UU 7 Tahun 2021"] == "pendek"


def test_combine_llm_drops_conflicting_leaves():
    a = LLMResult({"ptkp.diri": Decimal(54_000_000), "x": Decimal(1)}, {"ptkp.diri": "q"}, tokens=3)
    b = LLMResult({"x": Decimal(2), "ter_bulanan.A[0].persen": Decimal(0)}, tokens=4)
    m = combine_llm(a, b)
    assert m.values == {"ptkp.diri": Decimal(54_000_000), "ter_bulanan.A[0].persen": Decimal(0)}
    assert m.tokens == 7 and any(d.startswith("x:") for d in m.dropped)
    assert combine_llm(None, b) is b and combine_llm(a, None) is a


def test_own_table_picks_the_last_snapshot_before_a_date():
    snaps = [{"tanggal": None, "tabel": {"v": 0}}, {"tanggal": "2016-06-22", "tabel": {"v": 1}},
             {"tanggal": "2023-12-27", "tabel": {"v": 2}}]
    assert A.own_table(snaps, dt.date(2016, 6, 22)) == {"v": 0}
    assert A.own_table(snaps, dt.date(2016, 6, 22), inclusive=True) == {"v": 1}
    assert A.own_table(snaps, dt.date(2030, 1, 1)) == {"v": 2}


def test_ter_counterfactual_moves_every_bracket():
    raw = {"ter_bulanan": {"A": [{"batas_atas": 5_400_000, "persen": 0}, {"batas_atas": None, "persen": 34}]},
           "ter_harian": {"batas_bebas_harian": 450_000, "lapisan": [{"batas_atas": 450_000, "persen": 0.5}]}}
    m = A.ter_counterfactual(raw)
    assert m["ter_bulanan"]["A"] == [{"batas_atas": Decimal(6_480_000), "persen": Decimal(1)},
                                     {"batas_atas": None, "persen": Decimal(35)}]
    assert m["ter_harian"]["lapisan"] == [{"batas_atas": Decimal(540_000), "persen": Decimal("1.5")}]
    assert m["ter_harian"]["batas_bebas_harian"] == 450_000 and raw["ter_bulanan"]["A"][0]["persen"] == 0


def test_2024_case_gets_a_counterfactual_and_own_tables_replace_labels():
    docs = documents(load_events(None), load_labels())
    case = next(c for c in A.load_cases(None) if c["id"] == "a2024")
    plan = A.plan_case(case, docs, [])
    assert plan.adapted_ubah is not None and plan.adapted_ubah["ter_bulanan"] != plan.adapted["ter_bulanan"]
    own = [{"tanggal": None, "tabel": {"ptkp": {"diri": 54_000_000}}},
           {"tanggal": "2023-12-27", "tabel": {"ptkp": {"diri": 54_000_000}, "ter_bulanan": {"A": []}}}]
    p = A.plan_case(case, docs, [], own)
    assert p.patch_source == "sistem" and p.adapted_ubah is None
    assert p.adapted == own[1]["tabel"] and p.stale["ter_bulanan"] == {}


def test_lampiran_tables_are_read_only_for_ter_texts_and_need_a_local_pdf(tmp_path):
    from taxagent.corpus.text_source import SourceText
    from taxagent.update.backtest import _tables, pdf_table_reader

    seen, lines = [], []
    found = {"PP 58 Tahun 2023": SourceText("LAMPIRAN TARIF EFEKTIF BULANAN KATEGORI A " + LONG, "jdih",
                                            "andal", "j58"),
             "PMK 101 Tahun 2016": SourceText(LONG, "jdih", "andal", "j101")}
    assert _tables(found, None) == {}
    assert _tables(found, lambda src, text: seen.append(src.jdih_id) or "tabel") == {"PP 58 Tahun 2023": "tabel"}
    assert seen == ["j58"]
    reader = pdf_table_reader(None, progress=lines.append)
    assert reader(SourceText(LONG, "jdih", "andal", "tidak-ada-pdf"), LONG) is None
    assert lines and "PDF JDIH lokal tidak ada" in lines[0]


def test_cumulative_feed_to_answer_skips_undetected_documents_and_keeps_own_tables(tmp_path, monkeypatch):
    from taxagent.corpus.text_source import SourceText
    from taxagent.update import backtest as B

    docs = documents(load_events(None), load_labels())
    events = sorted((n for n, i in docs.items() if i["peran"] == "peristiwa"), key=lambda n: docs[n]["tanggal"])
    seen_text, hidden = events[0], events[1]

    class Corpus:
        def pick(self, name, dataset_text=None):
            return SourceText("Pasal 1 " + LONG, "jdih", "andal", None) if name in (seen_text, hidden) else None

    monkeypatch.setattr(B, "CorpusIndex", Corpus)
    monkeypatch.setattr(B, "detect", lambda d, t, x, c: {n: {"aturan": "dasar", "llm": None,
                                                              "masuk_antrean": n != hidden} for n in d
                                                          if d[n]["peran"] != "awal"})
    asked = []
    dataset = tmp_path / "dataset.json"
    dataset.write_text("[]", encoding="utf-8")
    h = B.cumulative(dataset, None, classifier=object(),
                     phase1_for=lambda name, nomor, title, text: asked.append(name) or [])
    by = {r["dokumen"]: r for r in h["run"]}
    assert by[hidden]["keputusan"] == "tidak_terdeteksi" and hidden not in asked
    assert asked == [seen_text] and h["fase1"] == "analisis dampak"
    assert h["tabel_sendiri"][0]["tanggal"] is None and h["tabel_sendiri"][0]["tabel"]
    json.dumps(h["tabel_sendiri"])
