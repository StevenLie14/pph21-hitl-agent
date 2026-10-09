from __future__ import annotations

from taxagent.corpus import chunking as P

PMK = ("PERATURAN MENTERI KEUANGAN NOMOR 1 TAHUN 2024 Menimbang: bahwa perlu. Mengingat: Undang-Undang. "
       "MEMUTUSKAN: Menetapkan: PERATURAN MENTERI KEUANGAN TENTANG PEMOTONGAN. "
       "Pasal 1 Dalam Peraturan Menteri ini yang dimaksud dengan pegawai adalah orang pribadi. "
       "Pasal 2 Pemotong sebagaimana dimaksud dalam Pasal 1 ayat (2) wajib memotong pajak. "
       "Pasal 3 (1) " + "Penghasilan bruto dihitung setiap bulan oleh pemberi kerja. " * 30 + "(2) " +
       "Biaya jabatan paling banyak enam juta rupiah setahun. " * 30 + "(3) Ketentuan lain diatur. "
       "Pasal 4 Peraturan Menteri ini mulai berlaku pada tanggal 1 Januari 2024. "
       "Agar setiap orang mengetahuinya, memerintahkan pengundangan. LAMPIRAN Tabel tarif efektif bulanan.")


def test_per_article_chunks_reference_not_title_and_correct_offset():
    pot = P.chunk(PMK)
    label = [p.label for p in pot]
    assert label[0] == "Pembukaan" and "Lampiran" in label
    assert any(x.startswith("Pasal 1") for x in label)
    assert not any("Pasal 1 ayat" in x and x.startswith("Pasal 2") for x in label)
    for p in pot:
        assert PMK[p.start:p.end] == p.text


def test_short_articles_merged_and_long_split_at_paragraphs():
    label = [p.label for p in P.chunk(PMK)]
    assert "Pasal 1-2" in label
    assert any(x.startswith("Pasal 3 ayat") for x in label)


def test_decree_with_diktum_and_unstructured_document():
    kmk = ("MEMUTUSKAN: Menetapkan: KEPUTUSAN MENTERI KEUANGAN.\nKESATU : " + "Menetapkan tarif. " * 40 +
           "\nKEDUA : " + "Keputusan ini mulai berlaku. " * 40)
    assert [p.label for p in P.chunk(kmk)][-2:] == ["Diktum Kesatu", "Diktum Kedua"]
    polos = "teks tanpa struktur " * 300
    assert {p.label for p in P.chunk(polos)} == {"Batang tubuh"}


def test_search_text_has_context_header():
    t = P.search_text("PMK 168 Tahun 2023", "Petunjuk Pelaksanaan", "Pasal 11", "Biaya  jabatan\n5%",
                      split=str.upper)
    assert t == "PMK 168 Tahun 2023, Petunjuk Pelaksanaan. Pasal 11. BIAYA JABATAN 5%"


def test_ocr_damaged_closing_still_separates_attachments():
    for penutup in ("Agar setiap o orang r mengetahuinya, memerintahkan pengundangan.",
                    "Agars setiap orang mengetahuinya, memerintahkan pengundangan."):
        teks = PMK.replace("Agar setiap orang mengetahuinya, memerintahkan pengundangan.", penutup)
        teks += " (1) Nama pemberi kerja (2) Alamat (3) NPWP"
        label = [p.label for p in P.chunk(teks)]
        assert label[-1] == "Lampiran" and not any("Pasal 4 ayat" in x for x in label), label
