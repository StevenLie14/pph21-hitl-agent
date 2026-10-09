from __future__ import annotations

import dataclasses

from taxagent.corpus.quality import QualityInput, Vocabulary, assess, check_identity, letter_words

TEKS = """PERATURAN MENTERI KEUANGAN REPUBLIK INDONESIA
NOMOR 101/PMK.010/2016
TENTANG PENYESUAIAN BESARNYA PENGHASILAN TIDAK KENA PAJAK
Menimbang bahwa dalam rangka menyesuaikan besarnya penghasilan tidak kena pajak perlu menetapkan peraturan.
MEMUTUSKAN: Menetapkan peraturan menteri keuangan tentang penyesuaian besarnya penghasilan tidak kena pajak.
Pasal 1
Penghasilan tidak kena pajak paling sedikit sebesar Rp54.000.000,00 (lima puluh empat juta rupiah) untuk diri
wajib pajak orang pribadi, ditambah Rp4.500.000,00 (empat juta lima ratus ribu rupiah) untuk wajib pajak kawin.
Pasal 2
Peraturan menteri ini mulai berlaku pada tanggal diundangkan dan berlaku untuk tahun pajak 2016.
Ditetapkan di Jakarta pada tanggal 27 Juni 2016
"""
KOS = Vocabulary([TEKS, TEKS, TEKS])
DOK = QualityInput("pmk-101", "jdih_ocr", TEKS, number=101, year=2016, pages=1)


def test_clean_text_reliable():
    h = assess(DOK, KOS)
    assert h.status == "andal", h.alasan
    assert h.ukuran["angka_terverifikasi"] == 2 and h.ukuran["identitas"] is True


def test_empty_text_unused():
    assert assess(dataclasses.replace(DOK, text="  "), KOS).status == "tidak_terpakai"


def test_broken_font_glyph_unused():
    sampah = "(cid:12)(cid:7)(cid:9) " * 60
    assert assess(dataclasses.replace(DOK, text=sampah + TEKS), KOS).status == "tidak_terpakai"


def test_number_not_matching_words_needs_check():
    h = assess(dataclasses.replace(DOK, text=TEKS.replace("Rp54.000.000,00", "Rp64.000.000,00")), KOS)
    assert h.status == "perlu_dicek" and "1 angka tidak cocok dengan terbilang" in h.alasan


def test_ocr_damaged_number_needs_check_even_once():
    h = assess(dataclasses.replace(DOK, text=TEKS.replace("tahun pajak 2016", "tahun pajak 2O16")), KOS)
    assert h.status == "perlu_dicek" and h.ukuran["angka_rusak"] == 1


def test_attached_rupiah_and_letter_article_not_ocr_error():
    h = assess(dataclasses.replace(DOK, text=TEKS + "\nPasal 11A berlaku untuk Rp4.500.000,00 (empat juta lima ratus ribu rupiah)."), KOS)
    assert h.ukuran["campuran_per_1000"] == 0 and h.ukuran["angka_rusak"] == 0


def test_many_damaged_words_need_check():
    rusak = TEKS.replace("penghasilan", "penghasi1an").replace("pajak", "paiak").replace("besarnya", "besamya")
    h = assess(dataclasses.replace(DOK, text=rusak), KOS)
    assert h.status == "perlu_dicek"
    assert "paiak" in h.ukuran["contoh_asing"] and "penghasi1an" in h.ukuran["contoh_campuran"]


def test_wrong_identity_needs_check():
    h = assess(dataclasses.replace(DOK, number=102), KOS)
    assert h.status == "perlu_dicek" and h.ukuran["identitas"] is False


def test_identity_number_year_style():
    assert check_identity("PERATURAN PEMERINTAH NOMOR 58 TAHUN 2023 TENTANG", 58, 2023)
    assert check_identity("KEPUTUSAN DIREKTUR JENDERAL PAJAK NOMOR : KEP- 185/PJ/2026", 185, 2026)
    assert not check_identity("PERATURAN PEMERINTAH NOMOR 158 TAHUN 2023", 58, 2023)
    assert check_identity("apa saja", None, None) is None
    assert check_identity("PERATURAN MENTERI KEUANGAN NOMOR 03/PMK.011/2012 TENTANG", 3, 2012)
    assert check_identity("SALIN AN PERATURAN MENTER! KEUANGAN NO MOR 64/PMK.010/2017", 64, 2017)
    assert check_identity("ABSTRAK PERATURAN ... 2024 PERMENKEU RI NO. 140, BN 2024/NO. 1110", 140, 2024)
    assert check_identity("PER-07/BC/2019 ... NOMOR PER-07/BC/2019", 7, 2019)
    assert not check_identity("KEPUTUSAN MENTERI KEUANGAN NOMOR: 295/KMK.014/1998", 298, 1998)
    assert not check_identity("NOMOR 103/PMK.03/2012", 3, 2012)


def test_pajak_go_id_body_skips_opening_closing_check():
    teks = "Surat ini menjelaskan " * 30
    assert assess(QualityInput("x", "pajak", teks), Vocabulary([teks] * 3)).status == "andal"
    rusak = teks + " tahun 2o22"
    assert assess(QualityInput("x", "pajak", rusak), Vocabulary([rusak] * 3)).status == "perlu_dicek"


def test_non_regulation_needs_no_article():
    teks = "Surat ini menjelaskan " * 30
    assert "tanpa pembuka dan penutup" in assess(QualityInput("x", "jdih_ocr", teks), Vocabulary([teks] * 3)).alasan
    assert assess(QualityInput("x", "jdih_ocr", teks, regulation=False), Vocabulary([teks] * 3)).status == "andal"


def test_leave_one_out_word_only_in_own_document_unknown():
    kos = Vocabulary([TEKS, "dokumen lain tanpa kata itu"])
    diri = set(letter_words(TEKS))
    assert kos.knows("penghasilan") is False
    assert Vocabulary([TEKS, TEKS, "lain"]).knows("penghasilan", diri) is False
    assert Vocabulary([TEKS, TEKS, TEKS]).knows("penghasilan", diri) is True
