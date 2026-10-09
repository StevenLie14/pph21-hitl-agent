from __future__ import annotations

from taxagent.corpus.relation_evidence import NormText, effective_date, evidence

KEPALA = ("Menimbang: bahwa perlu mengganti. Mengingat: 1. Peraturan Menteri Keuangan Nomor 252/PMK.03/2008 "
          "tentang Petunjuk Pelaksanaan; MEMUTUSKAN: Menetapkan: PERATURAN MENTERI KEUANGAN TENTANG PETUNJUK. ")
PENUTUP = ("BAB IX KETENTUAN PENUTUP Pasal 24 Pada saat Peraturan Menteri ini mulai berlaku: a. Peraturan Menteri "
           "Keuangan Nomor 250/PMK.03/2008 tentang Biaya Jabatan; b. Peraturan Menteri Keuangan Nomor 252/PMK.O3/2OO8 "
           "tentang Petunjuk Pelaksanaan; dan c. Pasal 5 dan Pasal 8 Peraturan Menteri Keuangan Nomor "
           "262/PMK.03/2010 tentang Tata Cara, dicabut dan dinyatakan tidak berlaku. Pasal 25 Peraturan Menteri ini "
           "mulai berlaku pada tanggal 1 Januari 2024. Agar setiap orang mengetahuinya, memerintahkan pengundangan.")
T = NormText.from_raw(KEPALA + PENUTUP)


def test_revocation_list_with_folded_ocr_numbers():
    b = evidence(T, "PMK 252 Tahun 2008", "mencabut")
    assert b["kelas"] == "eksplisit" and b["pasal"] == "Pasal 24"
    assert "dicabut dan dinyatakan tidak berlaku" in b["kutipan"]


def test_mention_in_mengingat_not_evidence():
    t = NormText.from_raw(KEPALA + "Pasal 1 Dalam Peraturan Menteri ini yang dimaksud dengan pegawai adalah orang pribadi.")
    assert evidence(t, "PMK 252 Tahun 2008", "mencabut")["kelas"] == "tanpa_bukti"


def test_articles_affected_by_partial_revocation_without_amending_article():
    b = evidence(T, "PMK 262 Tahun 2010", "mencabut_sebagian")
    assert b["kelas"] == "eksplisit" and b["pasal_terdampak"] == ["5", "8"]


def test_implied_via_amended_parent():
    t = NormText.from_raw("MEMUTUSKAN: Pasal 16 Pada saat Peraturan Menteri ini mulai berlaku, Peraturan Menteri Keuangan "
                          "Nomor 9/PMK.03/2021 tentang Insentif sebagaimana telah beberapa kali diubah terakhir dengan "
                          "Peraturan Menteri Keuangan Nomor 149/PMK.03/2021, dicabut dan dinyatakan tidak berlaku.")
    induk = {"PMK 82 Tahun 2021": {"PMK 9 Tahun 2021"}}
    b = evidence(t, "PMK 82 Tahun 2021", "mencabut", induk)
    assert b["kelas"] == "tersirat" and b["lewat"] == "PMK 9 Tahun 2021"
    assert evidence(t, "PMK 82 Tahun 2021", "mencabut")["kelas"] == "tanpa_bukti"


def test_amendment_title_without_word_diubah():
    t = NormText.from_raw("MEMUTUSKAN: Menetapkan: PERATURAN MENTERI KEUANGAN TENTANG PERUBAHAN ATAS PERATURAN MENTERI "
                          "KEUANGAN NOMOR 43/PMK.03/2009 TENTANG PAJAK PENGHASILAN. Pasal I Di antara Pasal 2 dan Pasal 3 "
                          "disisipkan 1 (satu) pasal.")
    b = evidence(t, "PMK 43 Tahun 2009", "mengubah")
    assert b["kelas"] == "eksplisit"


def test_effective_date():
    assert effective_date(T, "2023-12-28", "2023-12-27") == ("2024-01-01", "eksplisit")
    acak = NormText.from_raw("MEMUTUSKAN: Pasal 5 Pemerintah ini mulai berlaku pada Peraturan tanggal 1 Januari 2024. Agar")
    assert effective_date(acak, None, None) == ("2024-01-01", "eksplisit")
    n = NormText.from_raw("MEMUTUSKAN: Pasal 3 Peraturan ini mulai berlaku setelah 30 (tiga puluh) hari terhitung sejak "
                          "tanggal diundangkan. Agar setiap orang")
    assert effective_date(n, "2019-02-06", None) == ("2019-03-08", "n_hari")
    u = NormText.from_raw("MEMUTUSKAN: Pasal 2 Peraturan ini mulai berlaku pada tanggal diundangkan. Agar setiap orang")
    assert effective_date(u, "2020-05-01", None) == ("2020-05-01", "diundangkan")
