from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[1] / "taxagent" / "taxes" / "pph21" / "data"


def _load(name):
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


def test_shape():
    cases = _load("kasus_agent_uji_graf.yaml")["kasus"]
    assert len(cases) == 15
    assert len({c["id"] for c in cases}) == 15
    for c in cases:
        assert c["perilaku"] == "graf" and c["tag"] == ["uji_graf"]
        assert c["harus_memuat"] and all(isinstance(k, list) and k for k in c["harus_memuat"])
        assert c["dasar"]


def test_every_basis_is_a_checked_chain_relation():
    chain = _load("rantai_pph21.yaml")["relasi"]
    checked = [r for r in chain if r.get("cek") in ("cocok_teks", "tersirat")]
    assert len(checked) == len(chain)
    for c in _load("kasus_agent_uji_graf.yaml")["kasus"]:
        assert any(word in c["dasar"] for word in ("mencabut", "mengubah")), c["id"]


def test_no_overlap_with_development_questions():
    dev = " ".join(c["pertanyaan"] for c in _load("kasus_agent_graf.yaml")["kasus"]).lower()
    for target in ("252/pmk.03/2008", "250/pmk.03/2008", "262/pmk.03/2010", "152/pmk.010/2015", "122/pmk.010/2015",
                   "162/pmk.011/2012", "137/pmk.03/2005", "83/pmk.03/2009", "pp 149", "112/kmk.03/2001",
                   "pp 45 tahun 1994", "per-32/pj/2015", "per-14/pj/2013", "pmk 10 tahun 2025", "9/pmk.03/2021"):
        assert target not in dev
