from taxagent.monitor.graph_v2 import Plan, chunk, node_key, node_name, plan, write
from taxagent.monitor.relation_llm import Relation


def test_fixed_size_overlapping_chunks():
    p = chunk("a" * 3500, size=1500, overlap=200)
    assert [len(x) for x in p] == [1500, 1500, 900] and chunk("") == []


def test_name_and_key():
    assert node_name("PMK", 168, 2023) == "PMK 168 Tahun 2023" and node_name("PER", 16, 2016) == "PER 16/2016"
    assert node_key("PMK", 168, 2023) == "PMK|168|2023"


def test_plan_relations_with_evidence_and_compact_nodes():
    dok = {"PMK|101|2016": {"nama": "PMK 101 Tahun 2016", "teks": "Pasal 4 ... dicabut " * 10}}
    rel = {"PMK|101|2016": [Relation("mencabut", "PMK", 122, 2015, "Peraturan Menteri Keuangan Nomor 122/PMK.010/2015")]}
    portal = {"PMK|101|2016": {("mencabut", "PMK", 122, 2015)}}
    r = plan(dok, rel, portal, {"ptkp": {"deskripsi": "PTKP"}}, [("PMK|101|2016", "ptkp", []), ("X|1|1", "ptkp", [])],
             {"model": "m", "prompt": "v", "tanggal": "2026-10-08"})
    assert r.regulations["PMK|122|2015"]["ringkas"] is True and r.regulations["PMK|101|2016"]["ringkas"] is False
    e = r.relations[0]
    assert e["tipe"] == "MENCABUT" and e["properti"]["portal_setuju"] is True and e["properti"]["sumber"] == "llm_terverifikasi"
    assert len(r.defines) == 1
    assert all(p["peraturan"] == "PMK|101|2016" for p in r.chunks)


class Rekam:
    def __init__(self):
        self.cypher = []

    def run(self, cypher, **params):
        self.cypher.append(cypher)


def test_write_idempotent_using_merge():
    k = Rekam()
    hasil = write(k, Plan())
    assert hasil["relasi"] == 0
    assert all("CREATE CONSTRAINT" in c or "CREATE FULLTEXT" in c or "MERGE" in c for c in k.cypher)
