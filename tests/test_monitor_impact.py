import json

import pytest

from taxagent import cli
from taxagent.monitor import impact as D
from taxagent.monitor.classify import load_watchlist
from taxagent.monitor.classify_llm import LLMCache
from taxagent.monitor.identity import canon_id


@pytest.fixture(scope="module")
def graf():
    return D.build_graph(load_watchlist())


def test_graph_built_from_watchlist_and_code(graf):
    assert set(graf.regulations[canon_id("PMK 101 Tahun 2016")]) == {"ptkp"}
    assert {"ptkp", "biaya_jabatan", "mekanisme_pemotongan"} <= graf.functions["calc_annual"]
    assert graf.functions["calc_final"] >= {"pph_final_pesangon", "pph_final_manfaat_pensiun"}
    for e in load_watchlist().regulations:
        if e.role == "dasar":
            assert set(e.governs) <= set(graf.parameters), e.identity


def test_every_non_npwp_rate_function_linked_to_its_parameter(graf):
    with_npwp = {"calc_monthly_ter", "calc_annual", "calc_pensioner_annual", "calc_non_permanent_employee",
                 "calc_non_employee", "calc_commissioner", "calc_article17_direct"}
    assert {f for f in with_npwp if "non_npwp" not in graf.functions[f]} == set()


def test_transitive_derived_and_functions(graf):
    assert graf.descendants({"ptkp"}) == {"kategori_ter", "ter_bulanan"}
    assert graf.descendants({"biaya_jabatan"}) == set()
    assert "calc_annual" in graf.affected_functions({"ptkp"})
    assert "calc_final" not in graf.affected_functions({"ptkp"})


def test_without_self_drops_document_node(graf):
    ident = canon_id("PMK 101 Tahun 2016")
    assert ident in graf.regulations and ident not in graf.without(ident).regulations
    assert graf.without(None) is graf


TEKS_PTKP = (
    "PERATURAN MENTERI KEUANGAN NOMOR 9 TAHUN 2027 TENTANG PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK. "
    "Pasal 1 Penghasilan Tidak Kena Pajak per tahun diberikan paling sedikit sebesar Rp60.000.000,00 untuk diri "
    "Wajib Pajak orang pribadi. Pasal 2 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan "
    "Nomor 101/PMK.010/2016 tentang Penyesuaian Besarnya Penghasilan Tidak Kena Pajak dicabut dan dinyatakan tidak "
    "berlaku. Pasal 3 Peraturan Menteri ini mulai berlaku pada tanggal diundangkan."
)


def _klien(jawaban: dict, catat: list | None = None):
    def panggil(sistem, pengguna):
        if catat is not None:
            catat.append((sistem, pengguna))
        return {"teks": json.dumps(jawaban), "token_masuk": 1000, "token_keluar": 50}
    return D.MeteredClient(panggil, "tiruan", LLMCache(None))


def test_rules_use_text_relations_to_graph(graf):
    ident = canon_id("PMK 9 Tahun 2027")
    h = D.rule_impact("PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK", "", ident, TEKS_PTKP, load_watchlist(), graf)
    assert "ptkp" in h.keys and "ptkp" in h.from_relations
    assert h.tokens_in == 0


TEKS_UBAH_UU_PPH = (
    "Pasal 3 Beberapa ketentuan dalam Undang-Undang Nomor 7 Tahun 1983 tentang Pajak Penghasilan sebagaimana "
    "telah beberapa kali diubah terakhir dengan Undang-Undang Nomor 36 Tahun 2008 tentang Perubahan Keempat atas "
    "Undang-Undang Nomor 7 Tahun 1983 tentang Pajak Penghasilan diubah sebagai berikut: "
    "1. Ketentuan ayat (1) Pasal 4 diubah sehingga Pasal 4 berbunyi sebagai berikut: Pasal 4 (1) Yang menjadi "
    "objek pajak adalah penghasilan, termasuk natura dan/atau kenikmatan sebagaimana dimaksud dalam Pasal 7. "
    "2. Ketentuan ayat (1) Pasal 9 diubah sehingga berbunyi sebagai berikut: Pasal 9 (1) biaya. "
    "3. Di antara Pasal 20 dan Pasal 21 disisipkan 1 (satu) pasal, yakni Pasal 20A sehingga berbunyi sebagai "
    "berikut: Pasal 20A pajak. "
    "4. Di antara BAB VII dan BAB VIII disisipkan 1 (satu) BAB, yakni BAB VIIA sehingga berbunyi sebagai "
    "berikut: BAB VIIA PENCEGAHAN Pasal 32B pemerintah. "
    "Pasal 4 Beberapa ketentuan dalam Undang-Undang Nomor 8 Tahun 1983 tentang Pajak Pertambahan Nilai, sebagai "
    "berikut: 1. Ketentuan ayat (1) Pasal 7 diubah sehingga berbunyi sebagai berikut: Pasal 7 (1) tarif. "
    "Pasal 5 Undang-Undang ini mulai berlaku pada tanggal diundangkan. Agar setiap orang mengetahuinya"
)


def test_amended_articles_per_regulation_without_enclosing_article():
    from taxagent.monitor.text import extract
    e = extract(TEKS_UBAH_UU_PPH, canon_id("UU 7 Tahun 2021"))
    assert e.amended_articles == {canon_id("UU 7 Tahun 1983"): ["4", "9", "20A", "32B"]}


def test_article_map_gives_only_touched_article_keys(graf):
    uu_pph = canon_id("UU 7 Tahun 1983")
    h = D.rule_impact("HARMONISASI PERATURAN PERPAJAKAN", "", canon_id("UU 7 Tahun 2021"), TEKS_UBAH_UU_PPH,
                      load_watchlist(), graf.without(canon_id("UU 7 Tahun 2021")))
    assert h.from_relations == {"natura"}
    assert any("pasal diubah 4, 9, 20A, 32B; berdampak: 4" in a for a in h.reasons)
    assert set(graf.relation_keys(uu_pph, None)[0]) == {"tarif_pasal_17", "ptkp"}
    assert graf.relation_keys(uu_pph, ["7", "17A"])[0] == ["ptkp", "tarif_pasal_17"]


def test_graph_llm_drops_keys_without_verbatim_quote(graf):
    catat: list = []
    k = _klien({"key": [
        {"key": "ptkp", "kutipan": "Penghasilan Tidak Kena Pajak per tahun diberikan paling sedikit"},
        {"key": "biaya_jabatan", "kutipan": "biaya jabatan paling banyak Rp7.200.000"},
        {"key": "bukan_key", "kutipan": "Pasal 1"},
    ], "alasan": "PTKP"}, catat)
    h = D.graph_llm_impact("PENYESUAIAN PTKP", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, k, graf)
    assert h.keys == {"ptkp"}
    assert h.dropped_quotes == ["biaya_jabatan"] and h.unknown_keys == ["bukan_key"]
    assert h.derived == {"kategori_ter", "ter_bulanan"} and "calc_annual" in h.functions
    assert (h.tokens_in, h.tokens_out) == (1000, 50)
    sistem, pengguna = catat[0]
    assert "didefinisikan oleh" in sistem and "Fakta graf" in pengguna and "PMK 101 Tahun 2016" in pengguna


def test_quote_with_ellipsis_and_parallel_json_form(graf):
    teks_n = D._norm(TEKS_PTKP)
    assert D._quote_present("Penghasilan Tidak Kena Pajak per tahun ... untuk diri Wajib Pajak", teks_n)
    assert not D._quote_present("Penghasilan Tidak Kena Pajak ... biaya jabatan paling banyak", teks_n)
    assert not D._quote_present("Pasal 1", teks_n)
    k = _klien({"key": ["ptkp"], "kutipan": ["Penghasilan Tidak Kena Pajak per tahun diberikan paling sedikit"]})
    assert D.graph_llm_impact("X", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, k, graf).keys == {"ptkp"}


def test_graph_snippets_rotate_across_parameters(graf):
    teks = ("A" * 1200 + " penghasilan tidak kena pajak " + "x" * 900) * 6 + " biaya jabatan paling banyak " + "y" * 3000
    c = D.graph_excerpt(teks, graf, limit=3000, head=500, window=150)
    assert "biaya jabatan" in c
    assert c.startswith("A" * 500) and len(c) < 3000 + 20 * len(" [...] ")
    assert D.graph_excerpt("pendek", graf) == "pendek"


def test_filter_catalog_only_keys_whose_terms_exist(graf):
    assert D.candidates_from_text(TEKS_PTKP, graf) == ["ptkp"]
    catat: list = []
    k = _klien({"key": [{"key": "ptkp", "kutipan": "Penghasilan Tidak Kena Pajak per tahun diberikan"}]}, catat)
    h = D.graph_llm_impact("X", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, k, graf, filtered=True)
    assert h.llm_called and h.candidates == ["ptkp"] and h.keys == {"ptkp"}
    sistem = catat[0][0]
    assert "- ptkp:" in sistem and "- biaya_jabatan:" not in sistem


def test_filter_without_candidates_does_not_call_llm(graf):
    catat: list = []
    h = D.graph_llm_impact("BEA KELUAR", canon_id("PMK 7 Tahun 2027"), "tarif bea keluar atas ekspor", _klien({"key": []}, catat), graf, filtered=True)
    assert catat == [] and not h.llm_called and h.keys == set() and h.tokens_in == 0


def test_cascade_stops_at_rules_or_continues_to_llm(graf):
    catat: list = []
    k = _klien({"key": [{"key": "natura", "kutipan": "penghasilan dalam bentuk natura dan/atau kenikmatan"}]}, catat)
    wl = load_watchlist()
    a = D.cascade_impact("PENYESUAIAN PTKP", "", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, wl, k, graf)
    assert catat == [] and not a.llm_called and "ptkp" in a.keys and a.derived == {"kategori_ter", "ter_bulanan"}
    teks = "Pasal 1 Imbalan sehubungan dengan pekerjaan dalam bentuk lain merupakan penghasilan dalam bentuk natura dan/atau kenikmatan bagi pegawai."
    b = D.cascade_impact("PERLAKUAN PAJAK", "", canon_id("PMK 8 Tahun 2027"), teks, wl, k, graf)
    assert len(catat) == 1 and b.llm_called and b.keys == {"natura"}


def test_union_keeps_rule_keys_and_adds_llm_keys_on_full_text(graf):
    catat: list = []
    teks = TEKS_PTKP + " Pasal 4 Imbalan dalam bentuk natura dan/atau kenikmatan merupakan penghasilan pegawai."
    k = _klien({"key": [{"key": "natura", "kutipan": "Imbalan dalam bentuk natura dan/atau kenikmatan"}]}, catat)
    h = D.union_impact("PENYESUAIAN PTKP", "", canon_id("PMK 9 Tahun 2027"), teks, load_watchlist(), k, graf)
    assert len(catat) == 1 and h.llm_called and {"ptkp", "natura"} <= h.keys
    assert "Teks lengkap:" in catat[0][1] and "Pasal 4 Imbalan" in catat[0][1]
    assert h.tokens_in == 1000 and h.derived >= {"kategori_ter", "ter_bulanan"}


def test_union_splits_a_long_text_per_chapter(graf):
    catat: list = []
    bab = ["BAB I KETENTUAN UMUM Pasal 1 penghasilan dalam bentuk natura dan/atau kenikmatan. " + "x " * 40,
           "BAB II PENGHASILAN TIDAK KENA PAJAK Pasal 2 Penghasilan Tidak Kena Pajak per tahun. " + "y " * 40,
           "BAB III PENUTUP Pasal 3 mulai berlaku. " + "z " * 40]
    pieces = D.chapters(" ".join(bab), limit=200)
    assert len(pieces) == 3 and all(len(x) <= 200 for x in pieces) and pieces[1].startswith("BAB II")
    assert D.chapters("pendek", limit=200) == ["pendek"]
    assert [len(x) for x in D.chapters("a" * 450, limit=200)] == [200, 200, 50]
    k = _klien({"key": [{"key": "natura", "kutipan": "penghasilan dalam bentuk natura dan/atau kenikmatan"}]}, catat)
    h = D.union_impact("X", "", canon_id("PMK 8 Tahun 2027"), " ".join(bab), load_watchlist(), k, graf, limit=200)
    assert len(catat) == 2 and h.keys == {"natura"} and any(r.startswith("bagian 3/3") for r in h.reasons)


def test_llm_without_graph_does_not_verify_or_give_graph_context(graf):
    catat: list = []
    k = _klien({"key": ["ptkp", "biaya_jabatan", "asal"], "alasan": "x"}, catat)
    h = D.llm_impact("PENYESUAIAN PTKP", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, k, graf)
    assert h.keys == {"ptkp", "biaya_jabatan"} and h.unknown_keys == ["asal"]
    assert h.derived == set()
    assert "didefinisikan oleh" not in catat[0][0] and "Fakta graf" not in catat[0][1]


def test_invalid_answer_fails_safe(graf):
    k = D.MeteredClient(lambda s, p: {"teks": "bukan json"}, "tiruan", LLMCache(None))
    assert not D.llm_impact("X", None, "teks", k, graf).valid
    h = D.graph_llm_impact("X", canon_id("PMK 9 Tahun 2027"), TEKS_PTKP, k, graf)
    assert not h.valid and "ptkp" in h.keys


def test_impact_score_and_facility_violations():
    label = {"A": {"ptkp"}, "B": {"natura", "tarif_pasal_17"}}
    pred = {"A": {"ptkp"}, "B": {"natura", "ptkp"}, "F": {"ter_bulanan"}, "G": set()}
    d, nd = D.score(pred, label, {"F", "G"})
    assert (d.tp, d.fp, d.fn, d.exact) == (2, 1, 1, 1)
    assert (nd.violations, nd.fp, nd.exact) == (1, 1, 1)


def test_impact_label_uses_catalog_key(graf):
    for i, v in D.load_labels().items():
        assert set(v["key"]) <= set(graf.parameters), i


def test_cli_monitor_impact(tmp_path, monkeypatch):
    berkas = tmp_path / "set.yaml"
    berkas.write_text(
        "pajakgoid:\n"
        "- {id: PMK 9 Tahun 2027, judul: PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK, label: dasar}\n"
        "- {id: PMK 8 Tahun 2027, judul: PPH PASAL 21 DITANGGUNG PEMERINTAH, label: fasilitas}\n"
        "- {id: PMK 7 Tahun 2027, judul: BEA KELUAR, label: tidak_relevan}\n",
        encoding="utf-8",
    )
    label = tmp_path / "label.yaml"
    label.write_text("dasar:\n  PMK 9 Tahun 2027: {key: [ptkp], diverifikasi: true}\n", encoding="utf-8")
    dataset = tmp_path / "d.json"
    dataset.write_text(json.dumps([
        {"title": "PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK", "number": "9/PMK.03/2027", "full_text": TEKS_PTKP},
        {"title": "PPH PASAL 21 DITANGGUNG PEMERINTAH", "number": "8/PMK.03/2027", "full_text": "PPh Pasal 21 ditanggung pemerintah"},
    ]), encoding="utf-8")

    def panggil(sistem, pengguna):
        if "TIDAK KENA PAJAK" in pengguna:
            return {"teks": '{"key": [{"key": "ptkp", "kutipan": "Penghasilan Tidak Kena Pajak per tahun diberikan"}]}',
                    "token_masuk": 900, "token_keluar": 40}
        return {"teks": '{"key": []}', "token_masuk": 800, "token_keluar": 10}

    monkeypatch.setattr(D, "metered_langchain_call", lambda p, m: (panggil, "tiruan"))
    kode = cli.main([
        "monitor-impact", "--file", str(berkas), "--label", str(label), "--text-dataset", str(dataset),
        "--cache", str(tmp_path / "c.jsonl"), "--output", str(tmp_path / "out"), "--parallel", "1",
    ])
    assert kode == 0
    r = json.loads((tmp_path / "out" / "pantau_dampak.json").read_text(encoding="utf-8"))["ringkas"]
    assert r["llm_graf"]["dasar"]["tp"] == 1 and r["llm_graf"]["bukan_dasar"]["dokumen_dengan_key"] == 0
    assert r["llm"]["token_masuk"] == 1700 and r["aturan"]["token_masuk"] == 0
    md = (tmp_path / "out" / "pantau_dampak.md").read_text(encoding="utf-8")
    assert "Biaya dan latensi" in md and "turunan" in md

    kode = cli.main([
        "monitor-impact", "--file", str(berkas), "--label", str(label), "--text-dataset", str(dataset),
        "--cache", str(tmp_path / "c.jsonl"), "--output", str(tmp_path / "out2"), "--parallel", "1",
        "--arms", "aturan,gabungan_utuh",
    ])
    assert kode == 0
    r = json.loads((tmp_path / "out2" / "pantau_dampak.json").read_text(encoding="utf-8"))["ringkas"]
    assert set(r) == {"aturan", "gabungan_utuh"} and r["gabungan_utuh"]["dasar"]["tp"] == 1
    assert cli.main(["monitor-impact", "--file", str(berkas), "--label", str(label), "--text-dataset", str(dataset),
                     "--arms", "salah"]) == 3

    label.write_text("dasar: {}\n", encoding="utf-8")
    assert cli.main(["monitor-impact", "--file", str(berkas), "--label", str(label), "--text-dataset", str(dataset)]) == 3
