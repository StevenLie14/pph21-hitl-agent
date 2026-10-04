import json

import pytest

from taxagent import cli
from taxagent.monitor import classify_llm as KL
from taxagent.monitor.evaluation import (
    EvalItem,
    Prediction,
    SetResult,
    combine_or,
    flip_rate,
    mcnemar,
    score_llm,
)


def _llm_tetap(peta: dict[str, str], hitung: list | None = None):
    def panggil(sistem: str, pengguna: str) -> str:
        if hitung is not None:
            hitung.append(pengguna)
        for kata, kat in peta.items():
            if kata in pengguna:
                return json.dumps({"kategori": kat, "alasan": f"menyebut {kata}"})
        return '{"kategori": "tidak_relevan", "alasan": "lain"}'
    return panggil


def test_parse_valid_and_text_wrapped_answer():
    h = KL.parse_answer('Berikut jawabannya: {"kategori": "Fasilitas", "alasan": "DTP"} selesai')
    assert (h.category, h.reason, h.valid) == ("fasilitas", "DTP", True)


@pytest.mark.parametrize("mentah", ["", "bukan json", '{"kategori": "mungkin"}', '{"kategori": "dasar"'])
def test_invalid_answer_fails_safe_to_review(mentah):
    h = KL.parse_answer(mentah)
    assert h.category == "perlu_ditinjau" and not h.valid


def test_failed_call_fails_safe_and_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(KL.time, "sleep", lambda s: None)

    def rusak(s, p):
        raise TimeoutError("rate limit")
    cache = KL.LLMCache(tmp_path / "c.jsonl")
    h = KL.LLMClassifier(rusak, "tiruan", cache, attempts=2).classify("PMK 1 Tahun 2027", "Judul")
    assert h.category == "perlu_ditinjau" and "gagal" in h.reason
    assert not (tmp_path / "c.jsonl").exists()


def test_cache_prevents_repeat_calls_and_survives_new_process(tmp_path):
    berkas = tmp_path / "c.jsonl"
    hitung: list = []
    kl = KL.LLMClassifier(_llm_tetap({"PASAL 21": "dasar"}, hitung), "tiruan", KL.LLMCache(berkas))
    assert kl.classify("PMK 9 Tahun 2027", "TARIF PASAL 21").category == "dasar"
    assert kl.classify("PMK 9 Tahun 2027", "TARIF PASAL 21").category == "dasar"
    assert len(hitung) == 1
    kl2 = KL.LLMClassifier(_llm_tetap({}, hitung), "tiruan", KL.LLMCache(berkas))
    assert kl2.classify("PMK 9 Tahun 2027", "TARIF PASAL 21").category == "dasar"
    assert len(hitung) == 1


def test_cache_survives_truncated_line_and_locked_file(tmp_path, monkeypatch):
    berkas = tmp_path / "c.jsonl"
    berkas.write_text('{"kunci": "a", "mentah": "{}"}\n{"kunci": "b", "men', encoding="utf-8")
    cache = KL.LLMCache(berkas)
    assert cache.get("a") is not None and cache.get("b") is None

    import builtins
    asli = builtins.open

    def terkunci(p, mode="r", *a, **k):
        if "a" in mode:
            raise PermissionError(13, "Permission denied")
        return asli(p, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", terkunci)
    monkeypatch.setattr(KL.time, "sleep", lambda s: None)
    cache.put({"kunci": "c", "mentah": "{}"})
    assert cache.write_failures == 1 and cache.get("c") is not None


def test_cache_key_distinguishes_model_repeat_and_input():
    p = KL.user_message("PMK 1 Tahun 2027", "A")
    k = KL.LLMCache.make_key("m1", 0, p)
    assert k != KL.LLMCache.make_key("m2", 0, p)
    assert k != KL.LLMCache.make_key("m1", 1, p)
    assert k != KL.LLMCache.make_key("m1", 0, KL.user_message("PMK 1 Tahun 2027", "B"))


def test_prompt_not_tuned_from_test_set_errors():
    p = KL.SYSTEM_PROMPT.upper()
    for kata in ("CORETAX", "IBU KOTA", "NUSANTARA", "SISTEM INTI"):
        assert kata not in p


def _set(label_pred: list[tuple[str, str]], nama="uji") -> SetResult:
    return SetResult(nama, [
        Prediction(EvalItem(nama, f"PMK {i} Tahun 2027", f"judul {i}", lab), pred, [])
        for i, (lab, pred) in enumerate(label_pred)
    ])


def test_hybrid_or_prefers_rules_and_adds_missed():
    aturan = _set([("dasar", "dasar"), ("fasilitas", "tidak_relevan"), ("tidak_relevan", "tidak_relevan")])
    llm = _set([("dasar", "prosedural"), ("fasilitas", "fasilitas"), ("tidak_relevan", "tidak_relevan")])
    h = combine_or(aturan, llm)
    assert [p.category for p in h.predictions] == ["dasar", "fasilitas", "tidak_relevan"]
    assert h.predictions[1].reasons[0].startswith("LLM:")
    s = h.binary()
    assert (s.tp, s.fn) == (2, 0)


def test_exact_mcnemar():
    a = _set([("dasar", "tidak_relevan")] * 5 + [("tidak_relevan", "tidak_relevan")] * 3)
    b = _set([("dasar", "dasar")] * 5 + [("tidak_relevan", "tidak_relevan")] * 3)
    m = mcnemar(a, b)
    assert (m["hanya_a_benar"], m["hanya_b_benar"]) == (0, 5)
    assert m["p"] == pytest.approx(0.0625)
    assert mcnemar(a, a)["p"] == 1.0


def test_reversed_levels():
    r1 = _set([("dasar", "dasar"), ("dasar", "tidak_relevan")])
    r2 = _set([("dasar", "fasilitas"), ("dasar", "dasar")])
    assert flip_rate([r1, r2]) == (1, 2)


def test_llm_score_uses_same_input_as_rules(tmp_path):
    items = [EvalItem("uji", "PMK 5 Tahun 2027", "PEMBERIAN INSENTIF PPH PASAL 21", "fasilitas", "perihal x")]
    hitung: list = []
    kl = KL.LLMClassifier(_llm_tetap({"INSENTIF": "fasilitas"}, hitung), "tiruan", KL.LLMCache(None))
    h = score_llm(items, kl, workers=2)
    assert h.predictions[0].category == "fasilitas"
    assert hitung == [KL.user_message("PMK 5 Tahun 2027", "PEMBERIAN INSENTIF PPH PASAL 21", "perihal x")]


def test_text_prompt_category_definitions_equal_title_prompt():
    assert KL.TEXT_SYSTEM_PROMPT != KL.SYSTEM_PROMPT
    for bagian in ("- dasar:", "- fasilitas:", "- prosedural:", "- tidak_relevan:", "Jawab HANYA dengan JSON"):
        i, j = KL.SYSTEM_PROMPT.index(bagian), KL.TEXT_SYSTEM_PROMPT.index(bagian)
        assert KL.SYSTEM_PROMPT[i:i + 200] == KL.TEXT_SYSTEM_PROMPT[j:j + 200]
    for kata in ("CORETAX", "IBU KOTA", "NUSANTARA", "SISTEM INTI"):
        assert kata not in KL.TEXT_SYSTEM_PROMPT.upper()


def test_snippet_head_and_pasal_21_window():
    teks = "A" * 3000 + " ketentuan PPh Pasal 21 bagi pegawai " + "B" * 3000 + " Pasal 26 " + "C" * 5000
    c = KL.excerpt(teks, limit=3000, head=1000, window=100)
    assert c.startswith("A" * 1000) and " [...] " in c
    assert "Pasal 21 bagi pegawai" in c and "Pasal 26" in c
    assert len(c) <= 3000 + 2 * len(" [...] ")


def test_snippet_without_mention_and_short_text():
    assert KL.excerpt("pendek  sekali", limit=100) == "pendek sekali"
    assert KL.excerpt("x" * 500, limit=200, head=50) == "x" * 200


def test_text_arm_cache_key_does_not_collide_with_title_arm():
    p = KL.user_message("PMK 1 Tahun 2027", "A")
    assert KL.LLMCache.make_key("m", 0, p) != KL.LLMCache.make_key("m", 0, p, KL.TEXT_SYSTEM_PROMPT, KL.TEXT_PROMPT_VERSION)


def test_text_from_dataset_duplicate_titles_split_by_number_year_and_date(tmp_path):
    from taxagent.monitor.evaluation import texts_from_dataset

    berkas = tmp_path / "d.json"
    berkas.write_text(json.dumps([
        {"title": "Insentif  Pajak", "number": "86/PMK.03/2020", "date": "16-07-2020", "full_text": "teks 86"},
        {"title": "INSENTIF PAJAK", "number": "44/PMK.03/2020", "date": "27-04-2020", "full_text": "teks 44"},
        {"title": "Tata Cara", "number": "PER-05/PJ/2019", "date": "26-03-2019", "full_text": "teks per 5"},
        {"title": "Tata Cara", "number": "PER-08/PJ/2021", "date": "06-04-2021", "full_text": "teks per 8"},
        {"title": "Ganda Kosong", "number": "PMK-1/PMK.03/2021", "date": "01-01-2021", "full_text": "x"},
        {"title": "Ganda Kosong", "number": "1/PMK.03/2021", "date": "01-01-2021", "full_text": "teks lengkap"},
    ]), encoding="utf-8")
    items = [
        EvalItem("s", "PMK 44 Tahun 2020", "INSENTIF PAJAK", "fasilitas"),
        EvalItem("s", "PER-5/PJ/2019", "TATA CARA", "tidak_relevan"),
        EvalItem("s", "PMK 1 Tahun 2021", "GANDA KOSONG", "tidak_relevan"),
        EvalItem("s", "PMK 9 Tahun 2021", "TIDAK ADA", "tidak_relevan"),
    ]
    t = texts_from_dataset(items, berkas)
    assert t == {"PMK 44 Tahun 2020": "teks 44", "PER-5/PJ/2019": "teks per 5", "PMK 1 Tahun 2021": "teks lengkap"}


def test_pasal21_text_arm_and_llm_text_with_title_fallback():
    from taxagent.monitor.evaluation import score_article21_text, score_llm_text

    items = [
        EvalItem("s", "PMK 1 Tahun 2027", "KETENTUAN PERPAJAKAN", "prosedural"),
        EvalItem("s", "PMK 2 Tahun 2027", "BEA KELUAR", "tidak_relevan"),
        EvalItem("s", "PMK 3 Tahun 2027", "TANPA TEKS", "dasar"),
    ]
    teks = {"PMK 1 Tahun 2027": "bukti pemotongan PPh Pasal 21 ...", "PMK 2 Tahun 2027": "ekspor"}
    det = score_article21_text(items, teks)
    assert [p.category for p in det.predictions] == ["perlu_ditinjau", "tidak_relevan", "tidak_relevan"]

    cadangan = _set([("prosedural", "tidak_relevan"), ("tidak_relevan", "tidak_relevan"), ("dasar", "dasar")], "s")
    for p, it in zip(cadangan.predictions, items):
        p.item = it
    hitung: list = []
    kl = KL.LLMClassifier.with_text(_llm_tetap({"bukti pemotongan": "prosedural"}, hitung), "tiruan", KL.LLMCache(None))
    h = score_llm_text(items, kl, teks, cadangan, workers=1)
    assert [p.category for p in h.predictions] == ["prosedural", "tidak_relevan", "dasar"]
    assert h.predictions[2].reasons[0] == "(tanpa teks: lengan judul)"
    assert len(hitung) == 2 and all("Cuplikan teks:" in x for x in hitung)


def test_cli_monitor_evaluate_llm_with_fake_llm(tmp_path, monkeypatch, capsys):
    berkas = tmp_path / "set.yaml"
    berkas.write_text(
        "kecil:\n"
        "- {id: PMK 5 Tahun 2027, judul: PPH PASAL 21 DITANGGUNG PEMERINTAH, label: fasilitas}\n"
        "- {id: PMK 6 Tahun 2027, judul: KETENTUAN PERPAJAKAN DALAM RANGKA SISTEM BARU, label: prosedural}\n"
        "- {id: PMK 7 Tahun 2027, judul: TARIF BEA KELUAR, label: tidak_relevan}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(KL, "langchain_call", lambda p, m: (_llm_tetap({"SISTEM BARU": "prosedural"}), "tiruan"))
    kode = cli.main([
        "monitor-evaluate-llm", "--file", str(berkas), "--output", str(tmp_path / "out"),
        "--cache", str(tmp_path / "c.jsonl"), "--repeats", "2",
    ])
    assert kode == 0
    md = (tmp_path / "out" / "pantau_evaluasi_llm.md").read_text(encoding="utf-8")
    assert "McNemar" in md and "hibrida" in md and "Variansi LLM" in md
    data = json.loads((tmp_path / "out" / "pantau_evaluasi_llm.json").read_text(encoding="utf-8"))
    assert data["lengan"]["hibrida"]["kecil"]["biner"]["fn"] <= data["lengan"]["aturan"]["kecil"]["biner"]["fn"]
    assert cli.main(["monitor-evaluate-llm", "--file", str(berkas), "--set", "tidak_ada"]) == 3

    dataset = tmp_path / "d.json"
    dataset.write_text(json.dumps([
        {"title": "KETENTUAN PERPAJAKAN DALAM RANGKA SISTEM BARU", "number": "6/PMK.03/2027",
         "date": "", "full_text": "bukti pemotongan PPh Pasal 21 dibuat melalui SISTEM BARU"},
    ]), encoding="utf-8")
    kode = cli.main([
        "monitor-evaluate-llm", "--file", str(berkas), "--output", str(tmp_path / "out2"),
        "--cache", str(tmp_path / "c.jsonl"), "--text-dataset", str(dataset),
    ])
    assert kode == 0
    data = json.loads((tmp_path / "out2" / "pantau_evaluasi_llm.json").read_text(encoding="utf-8"))
    assert {"teks_pasal21", "llm_teks", "aturan+llm_teks"} <= set(data["lengan"])
    assert data["meta"]["cakupan teks per set"] == {"kecil": "1/3"}


def test_tool_arm_searches_reads_then_answers_and_caches(tmp_path):
    teks = "MENTERI KEUANGAN " + "isi umum " * 400 + "Pasal 21 penghasilan tidak kena pajak diubah menjadi Rp60.000.000"
    langkah = [
        {"aksi": "cari", "kueri": "penghasilan tidak kena pajak"},
        {"aksi": "baca", "posisi": 0},
        {"aksi": "selesai", "kategori": "dasar", "alasan": "mengubah PTKP"},
    ]
    pesan: list[str] = []

    def panggil(sistem: str, pengguna: str) -> str:
        pesan.append(pengguna)
        return json.dumps(langkah[len(pesan) - 1])

    kl = KL.LLMToolClassifier(panggil, "tiruan", KL.LLMCache(tmp_path / "c.jsonl"))
    h = kl.classify("PMK 1/2026", "Perubahan", "", teks)
    assert (h.category, h.valid) == ("dasar", True) and h.reason.endswith("[3 langkah]")
    assert "Rp60.000.000" in pesan[1] and "Langkah 2: baca 0" in pesan[2]
    kl2 = KL.LLMToolClassifier(lambda s, u: pytest.fail("tidak boleh memanggil LLM"), "tiruan",
                               KL.LLMCache(tmp_path / "c.jsonl"))
    assert kl2.classify("PMK 1/2026", "Perubahan", "", teks).category == "dasar"


def test_tool_arm_out_of_steps_fails_safe(tmp_path):
    kl = KL.LLMToolClassifier(lambda s, u: '{"aksi": "cari", "kueri": "pasal 21"}', "tiruan", KL.LLMCache(None),
                              max_steps=2)
    h = kl.classify("PMK 1/2026", "Judul", "", "teks pendek")
    assert h.category == "perlu_ditinjau" and not h.valid
