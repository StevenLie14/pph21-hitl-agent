from __future__ import annotations

import datetime as dt

import pytest

from taxagent.tools import regulation_graph as G

NODE = {
    "PMK 168 Tahun 2023": {"mulai": "2024-01-01", "url_berkas": "https://x/168.pdf", "punya_teks": True},
    "PMK 252 Tahun 2008": {"mulai": "2009-01-01"},
    "PMK 262 Tahun 2010": {"mulai": "2010-12-31"},
}
EDGE = [
    ("PMK 168 Tahun 2023", "MENCABUT", "PMK 252 Tahun 2008", {"bukti": "eksplisit", "tgl": "2024-01-01", "pasal": "Pasal 24"}),
    ("PMK 168 Tahun 2023", "MENCABUT_SEBAGIAN", "PMK 262 Tahun 2010",
     {"bukti": "eksplisit", "tgl": "2024-01-01", "pasal_terdampak": ["5", "8"]}),
]
POT = [
    ("PMK 168 Tahun 2023#10", "PMK 168 Tahun 2023", "Pasal 11", "Pasal 11 Biaya jabatan 5% paling banyak Rp6.000.000", 12),
    ("PMK 262 Tahun 2010#4", "PMK 262 Tahun 2010", "Pasal 5", "Pasal 5 Biaya jabatan pejabat negara", None),
    ("PMK 262 Tahun 2010#5", "PMK 262 Tahun 2010", "Pasal 6", "Pasal 6 Biaya jabatan pensiunan PNS", None),
    ("PMK 252 Tahun 2008#3", "PMK 252 Tahun 2008", "Pasal 2-3", "Pasal 2 Biaya jabatan lama Pasal 3", 4),
]

FAQ = [{"id": "faq-pph21#1", "pertanyaan": "Bagaimana menghitung biaya jabatan?", "jawaban": "Biaya jabatan " + "x" * 2000,
        "halaman": "FAQ PPh 21", "url": "https://www.pajak.go.id/id/faq-pph21", "tanggal_faq": "2023-05-01",
        "rujukan": ["PMK 252 Tahun 2008", "PMK 168 Tahun 2023"]}]


class Tiruan:
    def query(self, cypher, **p):
        if "MATCH (p:Regulation {key: $k}) RETURN" in cypher:
            n = NODE.get(p["k"])
            return [{"kunci": p["k"], "judul": "x", "stub": False, **n}] if n else []
        if "toLower(p.title)" in cypher:
            return []
        if "(a:Regulation)-[e]->(p:Regulation {key: k})" in cypher:
            return [{"k": k, "lawan": a, "tipe": t, **pr} for k in p["ks"] for a, t, z, pr in EDGE if z == k]
        if "(p:Regulation {key: k})-[e]->(z:Regulation)" in cypher:
            return [{"k": k, "lawan": z, "tipe": t, **pr} for k in p["ks"] for a, t, z, pr in EDGE if a == k]
        if "article_label STARTS WITH" in cypher:
            return [{"id": i, "label": lab, "teks": t, "halaman": h} for i, per, lab, t, h in POT if per == p["k"]]
        if "queryNodes('chunk_search'" in cypher:
            kata = p["q"].lower().split()
            return [{"id": i, "label": lab, "teks": t, "halaman": h, "score": float(sum(w in t.lower() for w in kata)),
                     "kunci": per, **NODE[per]} for i, per, lab, t, h in POT if any(w in t.lower() for w in kata)]
        if "queryNodes('faq_text'" in cypher:
            kata = p["q"].lower().split()
            return [{**f, "score": 1.0, "rujukan": [{"kunci": k, **NODE[k]} for k in f["rujukan"]]}
                    for f in FAQ if any(w in (f["pertanyaan"] + f["jawaban"]).lower() for w in kata)]
        if "UNWIND $ks AS k MATCH (p:Regulation {key: k}) RETURN" in cypher:
            return [{"kunci": k, **NODE[k]} for k in p["ks"] if k in NODE]
        return []


@pytest.fixture(autouse=True)
def klien():
    G.use_client(Tiruan())
    yield
    G.use_client(None)


def test_status_depends_on_date():
    sebelum = G.find_regulation(regulation="252/PMK.03/2008", date="2023-12-31")["peraturan"][0]
    sesudah = G.find_regulation(regulation="PMK 252 Tahun 2008", date="2024-01-01")["peraturan"][0]
    assert sebelum["status"] == "berlaku"
    assert (sesudah["status"], sesudah["oleh"]) == ("dicabut", ["PMK 168 Tahun 2023"])
    assert G.find_regulation(regulation="PMK 168 Tahun 2023", date="2023-12-15")["peraturan"][0]["status"] == \
        "belum_berlaku"


def test_wrong_and_missing_dates_returned_as_data():
    assert G.find_regulation(regulation="PMK 1 Tahun 2099")["berhasil"] is False
    assert "YYYY-MM-DD" in G.find_regulation(regulation="PMK 168 Tahun 2023", date="30/11/2023")["galat"]


def test_fetch_article_with_page_and_void_article_warning():
    h = G.get_article(regulation="PMK 168 Tahun 2023", article="11", date="2024-06-01")
    assert h["berhasil"] and h["halaman_pdf"] == 12 and h["tautan"].endswith("#page=12") and not h["peringatan"]
    g = G.get_article(regulation="PMK 262 Tahun 2010", article="Pasal 5", date="2024-06-01")
    assert g["status_peraturan"] == "berlaku_sebagian" and any("Pasal 5" in x for x in g["peringatan"])
    assert G.get_article(regulation="PMK 252 Tahun 2008", article="3")["label"] == ["Pasal 2-3"]


def test_search_text_drops_revoked_regulations_and_void_articles():
    h = G.search_text(query="biaya jabatan", date="2024-06-01")
    ids = [x["id"] for x in h["hasil"]]
    assert "PMK 168 Tahun 2023#10" in ids and "PMK 262 Tahun 2010#5" in ids
    assert "PMK 262 Tahun 2010#4" not in ids and "PMK 252 Tahun 2008#3" not in ids and h["dibuang_tidak_berlaku"] == 2
    semua = G.search_text(query="biaya jabatan", date="2024-06-01", in_force_only=False)
    assert len(semua["hasil"]) == 4


def test_check_citation_origin_and_status():
    hasil = [G.find_regulation(regulation="PMK 252 Tahun 2008")]
    d = dt.date(2025, 1, 1)
    assert G.check_citations("Biaya jabatan diatur PMK 252/PMK.03/2008.", hasil, d) == []
    assert G.check_citations("PMK 252/PMK.03/2008 masih berlaku untuk biaya jabatan.", hasil, d) == [
        "PMK 252 Tahun 2008 berstatus dicabut pada 2025-01-01 tetapi disebut masih berlaku"]
    assert G.check_citations("PMK 252/PMK.03/2008 sudah dicabut, jadi tidak berlaku saat ini.", hasil, d) == []
    assert "tidak berasal dari hasil tool" in G.check_citations("Lihat PMK 101 Tahun 2016.", hasil, d)[0]


def test_legal_basis_skill_results_count_as_sources():
    d = dt.date(2025, 1, 1)
    skill = {"berhasil": True, "topik": "ter", "rujukan": ["PP No. 58 Tahun 2023", "PMK No. 168 Tahun 2023"]}
    assert G.check_citations("Dasarnya PMK 168 Tahun 2023.", [skill], d) == []
    located = {"berhasil": True, "lokasi_dasar_hukum": [{"rujukan": "PMK No. 168 Tahun 2023 Pasal 10 ayat (2)",
                                                          "peraturan": "PMK 168 Tahun 2023"}]}
    assert G.check_citations("Dasarnya PMK 168 Tahun 2023.", [located], d) == []
    faq = {"berhasil": True, "hasil": [{"rujukan_faq": [{"dirujuk": "PMK 168 Tahun 2023"}]}]}
    assert "tidak berasal dari hasil tool" in G.check_citations("Dasarnya PMK 168 Tahun 2023.", [faq], d)[0]


def test_citation_with_no_abbreviation_is_read():
    d = dt.date(2025, 1, 1)
    hasil = [G.find_regulation(regulation="PMK 252 Tahun 2008")]
    assert "tidak berasal dari hasil tool" in G.check_citations("Lihat PMK No. 101 Tahun 2016.", hasil, d)[0]
    assert "tidak berasal dari hasil tool" in G.check_citations(
        "Rujukan: [PMK No. 101 Tahun 2016](https://x), hlm. 3.", hasil, d)[0]
    [(k, _)] = G.unstated_status("Dasarnya PMK No. 252/PMK.03/2008. Besarnya 5%.", d)
    assert k == "PMK 252 Tahun 2008"
    assert list(G._SENTENCE_END.split("Lihat PMK No. 252 Tahun 2008, hlm. 4. Lalu PMK 168 Tahun 2023.")) == [
        "Lihat PMK No. 252 Tahun 2008, hlm. 4.", "Lalu PMK 168 Tahun 2023."]


def test_unstated_status_is_checked_over_the_whole_answer():
    d = dt.date(2025, 1, 1)
    [(k, st)] = G.unstated_status("Biaya jabatan diatur PMK 252/PMK.03/2008.", d)
    assert (k, st["status"]) == ("PMK 252 Tahun 2008", "dicabut")
    for answer in ["PMK 252/PMK.03/2008 sudah dicabut sejak 2024. Yang Anda maksud adalah PMK 252/PMK.03/2008 "
                   "tentang biaya jabatan.",
                   "Pada 1 Januari 2025, PMK 252 Tahun 2008 berstatus berakhir. Dulu PMK 252 Tahun 2008 mengatur ini.",
                   "Dengan demikian, PMK 252 Tahun 2008 bukan aturan yang berlaku saat ini.",
                   "PMK 252 Tahun 2008 berstatus **dicabut**.",
                   "**Status PMK 252 Tahun 2008 per 1 Januari 2025: “dicabut”.**"]:
        assert G.unstated_status(answer, d) == [], answer
    assert G.unstated_status("Biaya jabatan diatur PMK 168 Tahun 2023.", d) == []


def test_status_stamp_follows_the_first_sentence_naming_the_regulation():
    d = dt.date(2025, 1, 1)
    answer = "Biaya jabatan diatur PMK 252/PMK.03/2008. Besarnya 5%."
    out = G.stamp_status(answer, G.unstated_status(answer, d), d)
    assert out == ("Biaya jabatan diatur PMK 252/PMK.03/2008. [Status per 2025-01-01 menurut graf peraturan: "
                   "PMK 252 Tahun 2008 dicabut sejak 2024-01-01 oleh PMK 168 Tahun 2023.] Besarnya 5%.")
    table = "\n".join(["Rincian:", "| Dasar | PMK 252 Tahun 2008 |", "|---|---|"])
    out = G.stamp_status(table, G.unstated_status(table, d), d)
    assert out.startswith(table) and out.endswith("PMK 252 Tahun 2008 dicabut sejak 2024-01-01 oleh PMK 168 Tahun 2023.]")
    assert G.stamp_status(answer, [], d) == answer


def test_agent_fixes_answer_once(monkeypatch):
    from langchain_core.messages import AIMessage

    from taxagent.agent import runner as R

    class LLM:
        def __init__(self):
            self.n = 0

        def invoke(self, pesan):
            self.n += 1
            if self.n == 1:
                return AIMessage(content="", tool_calls=[{"name": "find_regulation", "id": "t1",
                                                         "args": {"regulation": "PMK 252 Tahun 2008"}}])
            if self.n == 2:
                return AIMessage(content="PMK 252 Tahun 2008 masih berlaku untuk biaya jabatan.")
            return AIMessage(content="Dasarnya PMK 252 Tahun 2008.")

    monkeypatch.setattr("taxagent.tools.registry.graph_enabled", lambda: True)
    a = R.TaxAgent(llm=LLM())
    p = a.ask("apa dasar biaya jabatan?")
    assert p.citation_corrections and "disebut masih berlaku" in p.citation_corrections[0]
    assert not p.citation_unverified and p.status_stamped == ["PMK 252 Tahun 2008"]
    assert p.answer.startswith("Dasarnya PMK 252 Tahun 2008. [Status per ")
    assert "PMK 252 Tahun 2008 dicabut sejak 2024-01-01 oleh PMK 168 Tahun 2023.]" in p.answer


def test_unstated_status_is_stamped_without_a_correction_turn(monkeypatch):
    a = _citation_agent(monkeypatch, ["Dasarnya PMK 252 Tahun 2008.", "tidak boleh dipakai"],
                        lambda answer, results, d: [])
    p = a.ask("apa dasar biaya jabatan?")
    assert p.citation_corrections == [] and p.rounds == 2 and p.status_stamped == ["PMK 252 Tahun 2008"]
    assert p.answer.startswith("Dasarnya PMK 252 Tahun 2008. [Status per ") and "belum terverifikasi" not in p.answer


def test_search_faq_explanation_not_citation_source_and_stale_mark():
    h = G.search_faq(query="biaya jabatan", date="2024-06-01")
    assert h["berhasil"] and h["jenis"].startswith("penjelasan") and "bukan dasar hukum" in h["catatan"].lower()
    f = h["hasil"][0]
    assert f["tautan"].startswith("https://www.pajak.go.id") and f["jawaban_terpotong"] and len(f["jawaban"]) == G.FAQ_LIMIT
    assert {r["dirujuk"]: r["status"] for r in f["rujukan_faq"]} == {"PMK 252 Tahun 2008": "dicabut",
                                                                     "PMK 168 Tahun 2023": "berlaku"}
    assert len(h["peringatan"]) == 1 and "PMK 252 Tahun 2008 (dicabut)" in h["peringatan"][0]
    assert "sumber" not in h and "peraturan" not in h
    masalah = G.check_citations("Biaya jabatan diatur PMK 168 Tahun 2023.", [h], dt.date(2024, 6, 1))
    assert masalah and "tidak berasal dari hasil tool" in masalah[0]
    assert G.search_faq(query="  ")["berhasil"] is False


def test_calculation_result_legal_basis_status(monkeypatch):
    st = G.basis_status(["PMK No. 168 Tahun 2023 Pasal 15 ayat (1)", "PMK No. 252 Tahun 2008"], dt.date(2024, 12, 31))
    assert [(s["peraturan"], s["status"]) for s in st] == [("PMK 168 Tahun 2023", "berlaku"),
                                                           ("PMK 252 Tahun 2008", "dicabut")]
    assert G.basis_status(["UU PPh Pasal 21 ayat (5a)"], dt.date(2024, 12, 31)) == []
    from taxagent.taxes.pph21 import tools as T
    from taxagent.tools import registry as R

    monkeypatch.setitem(NODE, "PP 58 Tahun 2023", {"mulai": "2024-01-01"})
    monkeypatch.setattr(R, "graph_enabled", lambda: True)
    h = T.lookup_ter(status_ptkp="TK/0", penghasilan_bruto_sebulan=10_000_000, tahun_pajak=2024)
    assert h["status_dasar_hukum"] == [{"peraturan": "PP 58 Tahun 2023", "status": "berlaku", "pada": "2024-12-31",
                                        "oleh": []}]
    monkeypatch.setattr(R, "graph_enabled", lambda: False)
    assert "status_dasar_hukum" not in T.lookup_ter(status_ptkp="TK/0", penghasilan_bruto_sebulan=1, tahun_pajak=2024)


def test_amendment_chain_carries_counterpart_status():
    r = G.amendment_chain(regulation="PMK 168 Tahun 2023", date="2024-06-01")
    assert {x["peraturan"]: x["status_peraturan"] for x in r["mengubah_atau_mencabut"]} == {
        "PMK 252 Tahun 2008": "dicabut", "PMK 262 Tahun 2010": "berlaku_sebagian"}


def test_search_text_semantic_gemini_and_bm25_fallback(monkeypatch):
    class TiruanVektor(Tiruan):
        def query(self, cypher, **p):
            if "chunk_vector_gemini" in cypher:
                return [{"id": i, "label": lab, "teks": t, "halaman": h, "score": 0.9 - n / 10, "kunci": per, **NODE[per]}
                        for n, (i, per, lab, t, h) in enumerate(POT)]
            return super().query(cypher, **p)

    G.use_client(TiruanVektor())
    monkeypatch.setattr("taxagent.corpus.gemini_embed.query_vector", lambda teks: [0.1, 0.2])
    h = G.search_text(query="berapa batas biaya jabatan", date="2024-06-01")
    assert h["metode"] == "semantik Gemini"
    assert [(x["peraturan"], x["pasal"]) for x in h["hasil"]] == [("PMK 168 Tahun 2023", "Pasal 11"),
                                                                   ("PMK 262 Tahun 2010", "Pasal 6")]
    monkeypatch.setattr("taxagent.corpus.gemini_embed.query_vector", lambda teks: None)
    assert G.search_text(query="biaya jabatan", date="2024-06-01")["metode"] == "full-text BM25"


def test_gemini_query_vector_total_timeout_then_pause(monkeypatch):
    import importlib
    import time as _t

    import taxagent.corpus.gemini_embed as GE

    GE = importlib.reload(GE)
    monkeypatch.setattr(GE, "TIMEOUT_S", 0.2)
    monkeypatch.setattr(GE, "_api_key", lambda: "x")
    panggilan = []

    def lambat(*a, **k):
        panggilan.append(1)
        _t.sleep(1)

    monkeypatch.setattr("httpx.post", lambat)
    mulai = _t.monotonic()
    assert GE.query_vector("biaya jabatan") is None and _t.monotonic() - mulai < 0.8
    assert GE.query_vector("ptkp") is None and len(panggilan) == 1


def test_reference_location_page_article_and_no_guessing():
    class Klien:
        def query(self, cypher, **p):
            if "RETURN p.url AS url" in cypher:
                return [{"url": "https://jdih/dok/pmk-168", "url_berkas": "https://jdih/168.pdf"}] \
                    if p["k"] == "PMK 168 Tahun 2023" else []
            return [{"label": "Pasal 4", "halaman": 7}, {"label": "Pasal 5 ayat (1)", "halaman": 8},
                    {"label": "Pasal 5 ayat (3)", "halaman": 9}]

    G.use_client(Klien())
    try:
        lok = G.reference_locations(["PMK No. 168 Tahun 2023 Pasal 5 ayat (3) huruf d", "PMK No. 168 Tahun 2023",
                                     "UU PPh Pasal 17", "PMK No. 999 Tahun 2023 Pasal 1"])
    finally:
        G.use_client(None)
    assert lok[0] == {"rujukan": "PMK No. 168 Tahun 2023 Pasal 5 ayat (3) huruf d", "peraturan": "PMK 168 Tahun 2023",
                      "pasal": "5", "halaman_pdf": 8, "tautan": "https://jdih/168.pdf#page=8"}
    assert lok[1]["halaman_pdf"] is None and lok[1]["tautan"] == "https://jdih/dok/pmk-168"
    assert len(lok) == 2


def _citation_agent(monkeypatch, answers, check):
    from langchain_core.messages import AIMessage

    from taxagent.agent import runner as R

    class LLM:
        def __init__(self):
            self.n = 0

        def invoke(self, pesan, **_):
            self.n += 1
            if self.n == 1:
                return AIMessage(content="", tool_calls=[{"name": "find_regulation", "id": "t1",
                                                         "args": {"regulation": "PMK 252 Tahun 2008"}}])
            return AIMessage(content=answers[min(self.n - 2, len(answers) - 1)])

    monkeypatch.setattr("taxagent.tools.registry.graph_enabled", lambda: True)
    monkeypatch.setattr("taxagent.tools.regulation_graph.check_citations", check)
    return R.TaxAgent(llm=LLM())


def test_corrected_answer_is_checked_again_and_leftover_problems_are_shown(monkeypatch):
    a = _citation_agent(monkeypatch, ["Dasarnya PMK 252 Tahun 2008.", "Tetap PMK 252 Tahun 2008."],
                        lambda answer, results, d: ["PMK 252/PMK.03/2008 dicabut pada tanggal fakta"])
    p = a.ask("apa dasar biaya jabatan?")
    assert p.citation_corrections and p.citation_unverified == ["PMK 252/PMK.03/2008 dicabut pada tanggal fakta"]
    assert p.citation_checked
    assert p.answer.startswith("Tetap PMK 252 Tahun 2008.")
    assert "belum terverifikasi" in p.answer and "- PMK 252/PMK.03/2008 dicabut" in p.answer


def test_answer_is_marked_unchecked_when_the_checker_cannot_run(monkeypatch):
    def broken(answer, results, d):
        raise ConnectionError("graf mati")

    a = _citation_agent(monkeypatch, ["Dasarnya PMK 168 Tahun 2023."], broken)
    p = a.ask("apa dasar biaya jabatan?")
    assert not p.citation_checked and p.citation_unverified == [] and p.citation_corrections == []
    assert p.answer.startswith("Dasarnya PMK 168 Tahun 2023.") and "tidak diperiksa otomatis" in p.answer


def test_clean_answer_gets_no_note(monkeypatch):
    a = _citation_agent(monkeypatch, ["Dasarnya PMK 168 Tahun 2023."], lambda answer, results, d: [])
    p = a.ask("apa dasar biaya jabatan?")
    assert p.answer == "Dasarnya PMK 168 Tahun 2023." and p.citation_checked and not p.citation_unverified


def test_check_citation_article_level():
    d = dt.date(2025, 1, 1)
    pasal = G.get_article(regulation="PMK 168 Tahun 2023", article="11")
    hasil = [pasal, G.find_regulation(regulation="PMK 262 Tahun 2010")]
    assert G.check_citations("Biaya jabatan diatur Pasal 11 PMK 168/PMK.03/2023.", hasil, d) == []
    assert "tidak muncul di hasil tool" in G.check_citations("Lihat Pasal 12 PMK 168/PMK.03/2023.", hasil, d)[0]
    hasil_12 = hasil + [{"peraturan": "PMK 168 Tahun 2023", "catatan": "Pasal 99 disebut di sini"}]
    assert "tidak ada di teks" in G.check_citations("Lihat Pasal 99 PMK 168/PMK.03/2023.", hasil_12, d)[0]
    hasil_5 = hasil + [{"peraturan": "PMK 262 Tahun 2010", "catatan": "Pasal 5"}]
    assert "sudah dicabut" in G.check_citations("Dasarnya Pasal 5 PMK 262/PMK.011/2010.", hasil_5, d)[0]
    assert G.check_citations("Pasal 5 PMK 262/PMK.011/2010 sudah dicabut.", hasil_5, d) == []
    assert G.check_citations("PPh Pasal 21 dihitung menurut PMK 168/PMK.03/2023; tarif Pasal 17 dipakai.", hasil, d) == []


def test_cited_articles_forms():
    assert G._cited_articles("berasal dari **PMK No. 168 Tahun 2023 Pasal 10 ayat (2)**.") == [
        ("PMK 168 Tahun 2023", "10", "2")]
    assert G._cited_articles("Sumber: [PMK 168 Tahun 2023, Pasal 10](https://x)") == [("PMK 168 Tahun 2023", "10", None)]
    assert G._cited_articles("PP 58 Tahun 2023 mencabut **Pasal 2 ayat (3)** PP 80 Tahun 2010.") == [
        ("PP 80 Tahun 2010", "2", "3")]
    assert G._cited_articles("PPh Pasal 21 PMK 168 Tahun 2023 dan tarif Pasal 17 berlaku.") == []
    d = dt.date(2025, 1, 1)
    hasil = [G.find_regulation(regulation="PMK 262 Tahun 2010"), {"peraturan": "PMK 262 Tahun 2010", "catatan": "Pasal 5"}]
    assert G.check_citations("PMK 168 Tahun 2023 mencabut Pasal 5 PMK 262/PMK.011/2010.",
                             hasil + [G.find_regulation(regulation="PMK 168 Tahun 2023")], d) == []


def test_graph_ablation_offers_text_tools_only_and_measures_citations_without_correction(monkeypatch):
    from taxagent.tools.registry import all_specs, graph_tool_names

    monkeypatch.setenv("PPH21_GRAF_ABLASI", "1")
    assert graph_tool_names() == {"search_text", "get_article"}
    names = [fn.__name__ for fn, _, _ in all_specs(with_graph=True)]
    assert "find_regulation" not in names and "amendment_chain" not in names and "search_text" in names
    a = _citation_agent(monkeypatch, ["Dasarnya PMK 252 Tahun 2008."],
                        lambda answer, results, d: ["PMK 252/PMK.03/2008 dicabut pada tanggal fakta"])
    p = a.ask("apa dasar biaya jabatan?")
    assert p.answer == "Dasarnya PMK 252 Tahun 2008."
    assert not p.citation_corrections and not p.citation_unverified
    assert p.citation_audit == ["PMK 252/PMK.03/2008 dicabut pada tanggal fakta",
                                "PMK 252 Tahun 2008 berstatus dicabut tetapi statusnya tidak disebut"]
    assert not p.status_stamped
