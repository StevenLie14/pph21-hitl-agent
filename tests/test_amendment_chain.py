from __future__ import annotations

import yaml

from taxagent.taxes.pph21.calc.rates import DATA_DIR

DATA = yaml.safe_load((DATA_DIR / "rantai_pph21.yaml").read_text(encoding="utf-8"))
NOMOR = {p["nomor"] for p in DATA["peraturan"]}


def test_regulation_numbers_unique():
    assert len(NOMOR) == len(DATA["peraturan"])


def test_relations_refer_to_listed_regulations():
    for r in DATA["relasi"]:
        assert r["dari"] in NOMOR and r["ke"] in NOMOR, r
        assert r["dari"] != r["ke"], r


def test_valid_relation_field_values():
    for r in DATA["relasi"]:
        assert r["jenis"] in {"mencabut", "mencabut_sebagian", "mengubah", "ditetapkan_menjadi"}, r
        assert r["cek"] in {"belum", "cocok_teks", "beda", "tidak_ada_di_teks", "tersirat"}, r
        if r["cek"] in ("cocok_teks", "tersirat"):
            assert r["kutipan"] and r["pasal"], r
