from taxagent.update.llm import FULL_TEXT_CHARS, PROMPT_VERSION, excerpt, extract_llm, pieces, system_prompt


def _doc() -> str:
    preamble = " ".join(f"Menimbang huruf {i}: uang pesangon perlu diatur." for i in range(400))
    return preamble + " Pasal 3 Tarif atas uang pesangon sebesar 15% (lima belas persen) di atas Rp100.000.000,00."


def test_old_excerpt_lost_the_number_full_reading_keeps_it():
    doc = _doc()
    assert len(doc) > 6000
    assert "15%" not in excerpt(doc, ("pesangon",))
    assert pieces(doc, ("pesangon",)) == [" ".join(doc.split())]


def test_long_text_is_read_per_chapter_that_mentions_the_term():
    filler = "lain " * (FULL_TEXT_CHARS // 4)
    doc = f"BAB I UMUM {filler} BAB II TARIF uang pesangon 15% (lima belas persen) BAB III PENUTUP {filler}"
    got = pieces(doc, ("pesangon",))
    assert len(got) == 1 and "15%" in got[0] and len(got[0]) <= FULL_TEXT_CHARS


def test_extract_llm_merges_pieces_and_drops_conflicts():
    filler = "lain " * (FULL_TEXT_CHARS // 4)
    doc = (f"BAB I {filler} uang pesangon sebesar 5% (lima persen) dan 15% (lima belas persen) "
           f"BAB II {filler} uang pesangon sebesar 5% (lima persen) dan 25% (dua puluh lima persen)")
    answers = iter([
        {"nilai": [{"field": "pph_final_pesangon[1].persen", "nilai": 5, "kutipan": "uang pesangon sebesar 5% (lima persen)"},
                   {"field": "pph_final_pesangon[2].persen", "nilai": 15, "kutipan": "dan 15% (lima belas persen)"}]},
        {"nilai": [{"field": "pph_final_pesangon[1].persen", "nilai": 5, "kutipan": "uang pesangon sebesar 5% (lima persen)"},
                   {"field": "pph_final_pesangon[2].persen", "nilai": 25, "kutipan": "dan 25% (dua puluh lima persen)"}]},
    ])
    calls = []

    def client(system, user, version):
        calls.append(len(user))
        return next(answers), {"token_masuk": 1, "token_keluar": 1}

    h = extract_llm(doc, client, groups=["pph_final_pesangon"])
    assert len(calls) == 2
    assert str(h.values.get("pph_final_pesangon[1].persen")) == "5"
    assert "pph_final_pesangon[2].persen" not in h.values
    assert any("sumber berbeda" in d for d in h.dropped)


def test_prompt_is_about_the_text_not_an_excerpt():
    assert "cuplikan" not in system_prompt("pph_final_pesangon")
    assert "v3" in PROMPT_VERSION


def test_mutation_rereads_only_the_touched_group(monkeypatch):
    import taxagent.update.llm as L

    original = L.LLMResult(
        values={"ptkp.wajib_pajak_sendiri": 54000000, "biaya_jabatan.persen": 5, "bukan_pegawai.dpp_persen": 50},
        quotes={"ptkp.wajib_pajak_sendiri": "Rp54.000.000,00 untuk diri Wajib Pajak",
                "biaya_jabatan.persen": "biaya jabatan sebesar 5% (lima persen)",
                "bukan_pegawai.dpp_persen": "50% (lima puluh persen) dari jumlah penghasilan bruto"},
        tokens=99)
    asked = []

    def fake_extract(text, client, groups, m=None):
        asked.append(list(groups))
        return L.LLMResult(values={"ptkp.wajib_pajak_sendiri": 64800000}, tokens=7, group=list(groups))

    monkeypatch.setattr(L, "extract_llm", fake_extract)
    text = ("Rp64.800.000,00 untuk diri Wajib Pajak; biaya jabatan sebesar 5% (lima persen); "
            "50% (lima puluh persen) dari jumlah penghasilan bruto")
    h = L.reread_changed(original, text, None, ["ptkp", "biaya_jabatan", "bukan_pegawai"], {"ptkp"})
    assert asked == [["ptkp"]]
    assert h.values == {"ptkp.wajib_pajak_sendiri": 64800000, "biaya_jabatan.persen": 5, "bukan_pegawai.dpp_persen": 50}
    assert h.tokens == 7

    asked.clear()
    broken = text.replace("biaya jabatan sebesar 5%", "biaya jabatan sebesar 6%")
    h = L.reread_changed(original, broken, None, ["ptkp", "biaya_jabatan", "bukan_pegawai"], {"ptkp"})
    assert asked == [["ptkp", "biaya_jabatan"]]
    assert "biaya_jabatan.persen" not in h.values
