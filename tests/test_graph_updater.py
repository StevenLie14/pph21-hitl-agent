from decimal import Decimal

import pytest

from taxagent.monitor.memory_graph import from_texts
from taxagent.tools import regulation_graph as G
from taxagent.update.graph_updater import evidence, extract_with_graph, keys_from_graph, to_extraction_result
from taxagent.update.llm import LLMResult

TEKS_BARU = ("Pasal 1\n\nBesarnya penghasilan tidak kena pajak disesuaikan menjadi: a. Rp60.000.000,00 (enam puluh juta "
             "rupiah) untuk diri Wajib Pajak orang pribadi.\n\nPasal 2\n\nlain-lain. " + "isi pengisi " * 300)


@pytest.fixture()
def graf_hpp():
    dok = {"UU 9 Tahun 2027": {"teks": TEKS_BARU, "mulai": "2027-01-01"},
           "UU 7 Tahun 1983": {"teks": "UU PPh", "mulai": "1984-01-01"},
           "PMK 5 Tahun 2020": {"teks": "PMK lama", "mulai": "2020-01-01"}}
    rel = [{"dari": "UU 9 Tahun 2027", "jenis": "mengubah", "ke": "UU 7 Tahun 1983", "pasal_terdampak": ["7", "18"]},
           {"dari": "UU 9 Tahun 2027", "jenis": "mencabut_sebagian", "ke": "PMK 5 Tahun 2020", "pasal_terdampak": ["3"]},
           {"dari": "UU 9 Tahun 2027", "jenis": "mengatur_lebih_lanjut", "ke": "PMK 5 Tahun 2020"}]
    definisi = [("UU 7 Tahun 1983", "ptkp", ["7"]), ("UU 7 Tahun 1983", "tarif_pasal_17", ["17"]),
                ("UU 7 Tahun 1983", "natura", ["4"]), ("PMK 5 Tahun 2020", "biaya_jabatan", ["2"])]
    G.use_client(from_texts(dok, rel, definisi))
    yield
    G.use_client(None)


def test_graph_keys_filtered_per_article(graf_hpp):
    keys, jejak = keys_from_graph("UU 9 Tahun 2027")
    assert keys == ["ptkp"] and "Pasal 7" in jejak[0] and "mengubah UU 7 Tahun 1983" in jejak[0]


def test_evidence_from_chunks_containing_term(graf_hpp):
    c = evidence("UU 9 Tahun 2027", "ptkp")
    assert "penghasilan tidak kena pajak" in c and len(c) <= 6000 + 10


def test_empty_evidence_when_graph_unreachable():
    class Mati:
        def query(self, *a, **k):
            raise ConnectionError("server mati")
    G.use_client(Mati())
    try:
        assert evidence("UU 9 Tahun 2027", "ptkp") == ""
        assert keys_from_graph("UU 9 Tahun 2027")[0] == []
    finally:
        G.use_client(None)


class Klien:
    def __call__(self, sistem, pengguna, versi):
        assert "(dari graf)" in pengguna and versi.endswith("+graf")
        return {"nilai": [{"field": "ptkp.wajib_pajak_sendiri", "nilai": 60000000,
                           "kutipan": "a. Rp60.000.000,00 (enam puluh juta rupiah) untuk diri Wajib Pajak orang pribadi"}]}, {}


def test_graph_extract_verifies_against_full_text(graf_hpp):
    h = extract_with_graph("UU 9 Tahun 2027", TEKS_BARU, Klien(), ["ptkp"])
    assert h.values == {"ptkp.wajib_pajak_sendiri": Decimal(60000000)}


def test_to_extraction_result_dict_and_layers():
    h = LLMResult(values={
        "ptkp.wajib_pajak_sendiri": Decimal(60000000),
        "tarif_pasal_17[0].batas_atas": Decimal(60000000), "tarif_pasal_17[0].persen": Decimal(5),
        "tarif_pasal_17[1].batas_atas": None, "tarif_pasal_17[1].persen": Decimal(35),
        "pph_final_pesangon[0].persen": Decimal(0),
    })
    hasil = to_extraction_result(h, "Rp60.000.000,00 (enam puluh juta rupiah) 5% (lima persen)")
    t = {x.key: x.value for x in hasil.findings}
    assert t["ptkp"] == {"wajib_pajak_sendiri": 60000000}
    assert t["tarif_pasal_17"] == [{"batas_atas": 60000000, "persen": 5}, {"batas_atas": None, "persen": 35}]
    assert "pph_final_pesangon" not in t and any("pph_final_pesangon" in c for c in hasil.notes)
    assert Decimal(60000000) in hasil.verified


def test_to_extraction_result_carries_all_quotes_of_that_key():
    h = LLMResult(values={"ptkp.wajib_pajak_sendiri": Decimal(60000000), "biaya_jabatan.persen": Decimal(5)},
                  quotes={"biaya_jabatan.persen": "biaya jabatan 5%", "ptkp.wajib_pajak_sendiri": "Rp60.000.000,00 untuk diri"})
    t = {x.key: x.quote for x in to_extraction_result(h, "teks").findings}
    assert t == {"ptkp": "Rp60.000.000,00 untuk diri", "biaya_jabatan": "biaya jabatan 5%"}


def test_memory_graph_answers_all_agent_tools(graf_hpp):
    st = G.find_regulation(regulation="UU 7 Tahun 1983", date="2028-01-01")["peraturan"][0]
    assert st["status"] == "berlaku_diubah" and st["oleh"] == ["UU 9 Tahun 2027"]
    assert G.find_regulation(regulation="PMK 5 Tahun 2020", date="2028-01-01")["peraturan"][0]["status"] == \
        "berlaku_sebagian"
    p = G.get_article(regulation="UU 9 Tahun 2027", article="1", date="2028-01-01")
    assert p["berhasil"] and "Rp60.000.000,00" in p["teks"]
    t = G.search_text(query="penghasilan tidak kena pajak", regulation="UU 9 Tahun 2027", date="2028-01-01")
    assert t["hasil"] and t["hasil"][0]["peraturan"] == "UU 9 Tahun 2027"
    assert G.skill_value(key="ptkp", date="2024-06-01")["didefinisikan_oleh"][0]["peraturan"] == "UU 7 Tahun 1983"
