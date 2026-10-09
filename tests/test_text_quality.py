from collections import Counter

from taxagent.monitor.text_quality import Corpus, assess, compare, decide, internal_check, words

KORPUS = Corpus(["menteri keuangan menetapkan peraturan menteri"] * 50 + ["dilakukan pemotongan pasal 21"] * 50
                + ["diiakukan"])
FREK = KORPUS.frek


def test_word_positions():
    assert words("Pasal 21, ayat (1)") == [("pasal", 0, 5), ("21", 6, 8), ("ayat", 10, 14), ("1", 16, 17)]


def test_decide_frequency_and_spacing():
    assert decide(["menteri"], ["menter"], FREK) == "pajak"
    assert decide(["diiakukan"], ["dilakukan"], FREK) == "pdf"
    assert decide(["tambahan", "lembaran"], ["tambahanlembaran"], FREK) == "spasi"


def test_pdf_wins_only_for_whole_three_letter_words():
    f = Counter({"1": 1000, "l": 2})
    assert decide(["l"], ["1"], f) == "ragu"
    f = Counter({"tni": 500})
    assert decide(["tn"], ["tni"], f) == "ragu"


def test_compare_patches_pajak_text_with_winning_pdf_words():
    pajak = "Menteri Keuangan menetapkan, pemotongan diiakukan sesuai Pasal 21."
    pdf = "Menter Keuangan menetapkan, pemotongan dilakukan sesuai Pasal 21."
    h = compare(pajak, pdf, FREK)
    assert h.count() == Counter({"pajak": 1, "pdf": 1})
    assert h.best_text == "Menteri Keuangan menetapkan, pemotongan dilakukan sesuai Pasal 21."


def test_internal_number_and_closing_check():
    c = internal_check("sebesar Rp54.000.000,00 (lima puluh juta rupiah). Ditetapkan di Jakarta")
    assert c.digit_mismatches == 1 and c.has_enactment and not c.has_promulgation


def test_assess_records_coverage_and_missing_pdf():
    p = assess("X", "menteri keuangan " * 50, "menteri keuangan " * 50 + "lampiran tabel " * 200, KORPUS)
    assert any("lampiran" in c for c in p.notes) and p.sumber_utama == "jdih_htm"
    assert assess("X", "menteri keuangan " * 50, "menteri keuangan " * 50, KORPUS, "scan").sumber_utama == "pajak_dikoreksi_jdih"
    assert assess("X", "menteri keuangan " * 50, "menteri keuangan " * 50, KORPUS, "ocr").sumber_utama == "jdih_ocr"
    assert assess("X", "menteri keuangan " * 50, "menteri keuangan " * 50, KORPUS, "digital").sumber_utama == "jdih_digital"
    q = assess("Y", "menteri keuangan", None, KORPUS)
    assert q.sumber_utama == "pajak" and any("tidak tersedia" in c for c in q.notes)
    r = assess("Z", "menteri keuangan " * 50, "menteri " * 10, KORPUS)
    assert r.sumber_utama == "pajak_pdf_sebagian"


def test_pdf_base_patched_with_pajak_words_and_numbers_never_swapped():
    pajak = "Menteri Keuangan menetapkan tarif 50 persen."
    pdf = "Menter Keuangan menetapkan tarif 5046 persen."
    h = compare(pajak, pdf, FREK, base="pdf")
    assert h.best_text == "Menteri Keuangan menetapkan tarif 5046 persen."
    assert any(b.differing_numbers for b in h.differences)
