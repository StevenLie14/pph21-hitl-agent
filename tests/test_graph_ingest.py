import datetime as dt

from taxagent.corpus.ingest import Document, package, write
from taxagent.monitor.graph_ingest import ingest

ISI = "Ketentuan mengenai penghitungan pemotongan diatur sebagai berikut dengan rincian yang cukup panjang. " * 4
TEKS = (
    "PERATURAN MENTERI KEUANGAN REPUBLIK INDONESIA\nNOMOR 7 TAHUN 2027\n"
    "TENTANG PEMOTONGAN PAJAK PENGHASILAN PASAL 21\n\nDENGAN RAHMAT TUHAN YANG MAHA ESA\n"
    "MENTERI KEUANGAN REPUBLIK INDONESIA,\nMenimbang : a. bahwa untuk melaksanakan ketentuan Pasal 21 ayat (5) "
    "Undang-Undang Nomor 7 Tahun 1983 tentang Pajak Penghasilan, perlu menetapkan Peraturan Menteri;\n"
    "Mengingat : 1. Undang-Undang Nomor 7 Tahun 1983 tentang Pajak Penghasilan sebagaimana telah beberapa kali "
    "diubah terakhir dengan Undang-Undang Nomor 7 Tahun 2021 tentang Harmonisasi Peraturan Perpajakan;\n"
    "2. Peraturan Pemerintah Nomor 58 Tahun 2023 tentang Tarif Pemotongan;\n"
    "MEMUTUSKAN:\nMenetapkan : PERATURAN MENTERI KEUANGAN TENTANG PEMOTONGAN PAJAK PENGHASILAN PASAL 21.\n\n"
    "Pasal 1\n\nBiaya jabatan sebesar 5% (lima persen). " + ISI + "\n\n"
    "Pasal 2\n\nPada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor 168 Tahun 2023 "
    "tentang Petunjuk Pelaksanaan Pemotongan Pajak atas Penghasilan, dicabut dan dinyatakan tidak berlaku. " + ISI
    + "\n\nPasal 3\n\nPeraturan Menteri ini mulai berlaku pada tanggal 1 Januari 2028. " + ISI
    + "\n\nAgar setiap orang mengetahuinya, memerintahkan pengundangan.\n"
)
HAL = {"url": "https://jdih.kemenkeu.go.id/dok/pmk-7-tahun-2027", "nomor": "7 TAHUN 2027", "judul": "PMK 7/2027",
       "tgl_penetapan": "2027-12-01", "tgl_pengundangan": "2027-12-05",
       "relasi": [{"kode": "x", "nama": "Mencabut", "arah": "keluar", "jenis_efek": "mencabut",
                   "nomor": "Peraturan Menteri Keuangan Nomor 168 Tahun 2023", "slug": "pmk-168-tahun-2023",
                   "tgl_mulai_berlaku": "2027-12-05", "identitas": "PMK 168 Tahun 2023"}]}


def _jdih(teks=TEKS):
    return Document(key="PMK 7 Tahun 2027", source="jdih", id="pmk-7-tahun-2027", number="7 TAHUN 2027",
                    title="Pemotongan Pajak Penghasilan Pasal 21", kind="PMK", text=teks, text_source="lapisan_pdf",
                    pages=HAL)


def test_jdih_package_verified_claims_date_from_closing_article_and_chunks():
    p = package(_jdih())
    r = p.relations[("PMK 7 Tahun 2027", "mencabut", "PMK 168 Tahun 2023")]
    assert r["bukti"] == "eksplisit" and r["sumber"] == "jdih+teks" and r["tgl_efektif"] == "2028-01-01"
    assert p.nodes["mulai"] == "2028-01-01" and p.nodes["slug_jdih"] == "pmk-7-tahun-2027" and "id_jdih" not in p.nodes
    assert [c["label_pasal"] for c in p.chunks if c["label_pasal"].startswith("Pasal")][:1] == ["Pasal 1"]
    assert all(c["teks_cari"].startswith("PMK 7 Tahun 2027") for c in p.chunks)


def test_package_without_text_claims_unchecked():
    p = package(_jdih(teks=None))
    r = p.relations[("PMK 7 Tahun 2027", "mencabut", "PMK 168 Tahun 2023")]
    assert r["bukti"] == "belum_dicek" and not p.chunks and not p.nodes["punya_teks"]
    assert p.nodes["mulai"] == "2027-12-05" and any("tanpa teks" in c for c in p.notes)


def test_pajak_package_relations_from_text_and_labels():
    d = Document(key="PER 9 Tahun 2027", source="pajak", id="per-9-pj-2027", number="PER-9/PJ/2027",
                 title="Pajak Penghasilan", kind="Peraturan Dirjen Pajak", text=TEKS, text_source="pajak.go.id",
                 detail={"url": "https://www.pajak.go.id/id/peraturan/per-9-pj-2027", "status": "Berlaku",
                         "tanggal": "2027-12-01"})
    p = package(d)
    assert p.nodes["label_pajak"] == "Berlaku" and p.nodes["slug_pajak"] == "per-9-pj-2027"
    r = p.relations[("PER 9 Tahun 2027", "mencabut", "PMK 168 Tahun 2023")]
    assert r["sumber"] == "teks" and r["bukti"] == "eksplisit"


class Klien:
    def __init__(self, node=None, ada=None):
        self.node, self.ada, self.tulis = node or {}, ada or {}, []

    def query(self, cypher, **p):
        if "RETURN p.stub AS stub, p.doc_source AS sumber" in cypher:
            return [self.node[p["k"]]] if p["k"] in self.node else []
        if "RETURN p.stub AS stub, p.has_text AS teks" in cypher:
            n = self.node.get(p["k"])
            return [{"stub": n["stub"], "teks": n["punya_teks"]}] if n else []
        if "WHERE type(e) = x.tipe" in cypher:
            return [{"dari": x["dari"], "tipe": x["tipe"], "ke": x["ke"], "bukti": self.ada[(x["dari"], x["tipe"], x["ke"])]}
                    for x in p["ps"] if (x["dari"], x["tipe"], x["ke"]) in self.ada]
        if "MENGUBAH*1..3" in cypher:
            return []
        if "RETURN p.key AS kunci, p.start AS mulai" in cypher:
            return [{"kunci": k, "mulai": None, "berlaku_sampai": None, "label_pajak": None} for k in p["ks"]]
        return []

    def run(self, cypher, **p):
        self.tulis.append((cypher, p))


def test_write_upsert_without_clearing_and_records_insert():
    k = Klien()
    h = write(k, package(_jdih()), {"commit": "abc"}, dt.date(2028, 2, 1))
    teks = " ".join(c for c, _ in k.tulis)
    assert "DETACH DELETE n" not in teks and "MERGE (a)-[e:MENCABUT]->(z)" in teks and "CREATE (m:Ingest)" in teks
    assert h["node_baru"] and h["edge_ditulis"] == ["PMK 7 Tahun 2027 -mencabut-> PMK 168 Tahun 2023 (eksplisit)"]
    assert h["status_dihitung_ulang"] == 2 and h["potongan"] > 0


def test_write_never_downgrades_old_edge_evidence_and_pajak_never_overwrites_jdih():
    k = Klien(ada={("PMK 7 Tahun 2027", "MENCABUT", "PMK 168 Tahun 2023"): "eksplisit"})
    h = write(k, package(_jdih(teks=None)), {})
    assert h["edge_ditulis"] == [] and "sudah ada (eksplisit)" in h["edge_dilewati"][0]
    k = Klien(node={"PER 9 Tahun 2027": {"stub": False, "sumber": "jdih", "punya_teks": True}})
    d = Document(key="PER 9 Tahun 2027", source="pajak", id="s", text=TEKS)
    assert "JDIH" in write(k, package(d), {})["dilewati"] and not k.tulis


def test_insert_skips_existing_documents_and_dry_run():
    k = Klien(node={"PMK 7 Tahun 2027": {"stub": False, "sumber": "jdih", "punya_teks": True}})
    assert ingest([_jdih()], k) == [{"kunci": "PMK 7 Tahun 2027", "dilewati": "sudah ada di graf"}]
    k = Klien(node={"PMK 7 Tahun 2027": {"stub": True, "sumber": None, "punya_teks": False}})
    [h] = ingest([_jdih()], k, dry_run=True)
    assert h["kering"] and h["relasi"] and not k.tulis


def test_legal_basis_menimbang_and_mengingat():
    p = package(_jdih())
    d = {(x["ke"], x["bagian"]): x for x in p.basis}
    assert d[("UU 7 Tahun 1983", "menimbang")]["peran"] == "delegasi"
    assert d[("UU 7 Tahun 1983", "menimbang")]["pasal"] == ["21"]
    assert d[("UU 7 Tahun 1983", "mengingat")]["peran"] == "pokok"
    assert d[("UU 7 Tahun 2021", "mengingat")]["peran"] == "perubahan"
    assert d[("PP 58 Tahun 2023", "mengingat")]["peran"] == "pokok"
    assert ("PMK 168 Tahun 2023", "mengingat") not in d


def test_legal_basis_tool_both_directions():
    from taxagent.monitor.memory_graph import from_texts
    from taxagent.tools import regulation_graph as G

    G.use_client(from_texts({"PMK 7 Tahun 2027": {"teks": TEKS, "mulai": "2028-01-01"},
                             "UU 7 Tahun 1983": {"teks": "UU PPh", "mulai": "1984-01-01"}}))
    try:
        h = G.regulation_legal_basis(regulation="PMK 7 Tahun 2027", date="2028-06-01")
        assert [x["peraturan"] for x in h["dasar"]][:2] == ["UU 7 Tahun 1983", "UU 7 Tahun 1983"]
        assert h["dasar"][0]["pasal"] == ["21"] and h["dasar"][0]["status"] == "berlaku"
        u = G.regulation_legal_basis(regulation="UU 7 Tahun 1983", date="2028-06-01")
        assert u["pelaksana_berlaku"][0]["peraturan"] == "PMK 7 Tahun 2027" and u["jumlah_pelaksana"]["berlaku"] == 1
        assert G.regulation_legal_basis(regulation="UU 7 Tahun 1983", date="2027-06-01")["jumlah_pelaksana"]["berlaku"] == 0
    finally:
        G.use_client(None)
