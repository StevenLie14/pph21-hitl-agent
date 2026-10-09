from __future__ import annotations

from taxagent.corpus.relation_evidence import NormText
from taxagent.corpus.relation_text import find_relations, pajak_status

PER = ("Mengingat: Peraturan Direktur Jenderal Pajak Nomor PER-9/PJ/2020 tentang Tata Cara; MEMUTUSKAN: Menetapkan: "
       "PERATURAN DIREKTUR JENDERAL PAJAK TENTANG BUKTI POTONG. Pasal 1 Bukti potong dibuat berdasarkan Peraturan "
       "Menteri Keuangan Nomor 168 Tahun 2023 dan diterbitkan secara elektronik. Pasal 20 Pada saat Peraturan "
       "Direktur Jenderal ini mulai berlaku: a. Peraturan Direktur Jenderal Pajak Nomor PER-5/PJ/2017 tentang Bukti "
       "sebagaimana telah diubah dengan Peraturan Direktur Jenderal Pajak Nomor PER-9/PJ/2020; dan b. Pasal 3 dan "
       "Pasal 7 Peraturan Direktur Jenderal Pajak Nomor PER-22/PJ/2021 tentang Pelaporan, dicabut dan dinyatakan "
       "tidak berlaku. Pasal 21 Peraturan ini mulai berlaku pada tanggal ditetapkan.")


def _rel():
    rel, sisa = find_relations(NormText.from_raw(PER), "PER-10/PJ/2024")
    return {(r["ke"], r["jenis"]): r for r in rel}, sisa


def test_explicit_base_implied_amender():
    r, _ = _rel()
    assert r[("PER-5/PJ/2017", "mencabut")]["kelas"] == "eksplisit"
    x = r[("PER-9/PJ/2020", "mencabut")]
    assert x["kelas"] == "tersirat" and x["lewat"] == "PER-5/PJ/2017"


def test_article_before_target_name_means_partial_revocation():
    r, _ = _rel()
    x = r[("PER-22/PJ/2021", "mencabut_sebagian")]
    assert x["pasal_terdampak"] == ["3", "7"]


def test_legal_basis_and_mengingat_not_target():
    r, _ = _rel()
    assert not any(k[0] == "PMK 168 Tahun 2023" for k in r)
    assert len(r) == 3


def test_transitional_provision_without_period_not_revocation():
    t = NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN DIREKTUR JENDERAL PAJAK TENTANG PEDOMAN TEKNIS. BAB X KETENTUAN "
        "PERALIHAN Pasal 27 Dengan berlakunya Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang "
        "Penyesuaian Besarnya Penghasilan Tidak Kena Pajak, maka penghitungan PPh Pasal 21 untuk Tahun Pajak 2015 "
        "dilakukan berdasarkan Peraturan ini BAB XI KETENTUAN PENUTUP Pasal 28 Pada saat berlakunya Peraturan "
        "Direktur Jenderal Pajak ini, Peraturan Direktur Jenderal Pajak Nomor PER-31/PJ/2012 tentang Pedoman "
        "Teknis Pemotongan Pajak Penghasilan Pasal 21 dicabut dan dinyatakan tidak berlaku.")
    rel, _ = find_relations(t, "PER-32/PJ/2015")
    assert {(r["ke"], r["jenis"]) for r in rel} == {("PER-31/PJ/2012", "mencabut")}


def test_other_regulation_chapter_reference_not_chapter_title():
    t = NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN PEMERINTAH TENTANG PENDANAAN PENDIDIKAN. Pasal 86 Pada saat Peraturan "
        "Pemerintah ini mulai berlaku, Bab XI Peraturan Pemerintah Nomor 28 Tahun 1990 tentang Pendidikan Dasar, "
        "Bab XII Peraturan Pemerintah Nomor 60 Tahun 1999 tentang Pendidikan Tinggi dinyatakan tidak berlaku.")
    rel, _ = find_relations(t, "PP 48 Tahun 2008")
    assert {r["ke"] for r in rel} == {"PP 28 Tahun 1990", "PP 60 Tahun 1999"}


def test_own_article_reference_before_target_does_not_reject_target():
    t = NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: UNDANG-UNDANG TENTANG BPJS. Pasal 69 Pada saat mulai beroperasinya BPJS "
        "Ketenagakerjaan sebagaimana dimaksud dalam Pasal 64, Undang-Undang Nomor 3 Tahun 1992 tentang Jaminan "
        "Sosial Tenaga Kerja dicabut dan dinyatakan tidak berlaku.")
    rel, _ = find_relations(t, "UU 24 Tahun 2011")
    assert {(r["ke"], r["jenis"]) for r in rel} == {("UU 3 Tahun 1992", "mencabut")}


def test_own_article_paragraph_reference_not_partial_revocation():
    t = NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN PEMERINTAH TENTANG PERSERO. Pasal 5 Terhitung mulai saat dibubarkannya "
        "PERUM PAL sebagaimana dimaksud dalam ayat (2) Pasal 1, Peraturan Pemerintah Nomor 14 Tahun 1978 dan semua "
        "peraturan pelaksanaannya dinyatakan tidak berlaku lagi.")
    rel, _ = find_relations(t, "PP 4 Tahun 1980")
    assert {(r["ke"], r["jenis"]) for r in rel} == {("PP 14 Tahun 1978", "mencabut")}


def test_revoked_paragraph_recorded_per_paragraph():
    t = NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN PEMERINTAH TENTANG TARIF. Pasal 4 Pada saat Peraturan Pemerintah ini "
        "mulai berlaku, Pasal 2 ayat (3) Peraturan Pemerintah Nomor 80 Tahun 2010 tentang Tarif Pemotongan dicabut "
        "dan dinyatakan tidak berlaku.")
    rel, _ = find_relations(t, "PP 58 Tahun 2023")
    assert [(r["ke"], r["jenis"], r["pasal_terdampak"]) for r in rel] == [
        ("PP 80 Tahun 2010", "mencabut_sebagian", ["2(3)"])]


def test_sentence_without_number_becomes_rest_and_perppu_enactment():
    t = NormText.from_raw("MEMUTUSKAN: Menetapkan: UNDANG-UNDANG TENTANG PENETAPAN PERATURAN PEMERINTAH PENGGANTI "
                          "UNDANG-UNDANG NOMOR 2 TAHUN 2022 TENTANG CIPTA KERJA MENJADI UNDANG-UNDANG. Pasal II Peraturan "
                          "Direktur Jenderal Pajak tentang pedoman teknis dicabut dan dinyatakan tidak berlaku.")
    rel, sisa = find_relations(t, "UU 6 Tahun 2023", "Undang-Undang")
    assert [(r["ke"], r["jenis"], r.get("arah")) for r in rel] == [("PERPPU 2 Tahun 2022", "ditetapkan_menjadi",
                                                                    "masuk")]
    assert len(sisa) == 1


def test_pajak_status_only_label_or_conflict():
    s = {x["kunci"]: x for x in pajak_status([("PER-14/PJ/2013", "Aktif"), ("PER-32/PJ/2015", "Dicabut"),
                                              ("KEP-1/PJ/1999", "Dicabut"), ("PER-1/PJ/2020", "Aktif")],
                                             {"PER-14/PJ/2013", "PER-32/PJ/2015"})}
    assert s["PER-14/PJ/2013"]["konflik"] and s["PER-14/PJ/2013"]["sumber"] == "teks"
    assert s["KEP-1/PJ/1999"]["sumber"] == "status_pajak_go_id"
    assert s["PER-32/PJ/2015"]["sumber"] == "teks" and "PER-1/PJ/2020" not in s


def _relasi(teks: str, diri: str) -> dict[str, tuple[str, str]]:
    rel, _ = find_relations(NormText.from_raw("MEMUTUSKAN: Menetapkan: " + teks), diri)
    return {r["ke"]: (r["jenis"], r["kelas"]) for r in rel}


def test_amendment_history_list_by_title_list_and_implied():
    r = _relasi("Pasal I Peraturan Pemerintah Nomor 14 Tahun 1993 tentang Penyelenggaraan Program Jaminan Sosial Tenaga "
             "Kerja sebagaimana telah beberapa kali diubah dengan Peraturan Pemerintah: a. Nomor 79 Tahun 1998; "
             "b. Nomor 64 Tahun 2005; c. Nomor 53 Tahun 2012, diubah sebagai berikut:", "PP 84 Tahun 2013")
    assert r["PP 14 Tahun 1993"] == ("mengubah", "eksplisit")
    assert r["PP 64 Tahun 2005"] == ("mengubah", "tersirat") and "UU 64 Tahun 2005" not in r


def test_amended_eight_times_with_implied():
    r = _relasi("Pasal I Beberapa ketentuan dalam Peraturan Menteri Keuangan Nomor 92/PMK.02/2005 tentang Penetapan Jenis "
             "Barang Ekspor yang telah delapan kali diubah dengan Peraturan Menteri Keuangan: a. Nomor "
             "130/PMK.010/2005; b. Nomor 83/PMK.02/2007, diubah sebagai berikut", "PMK 72 Tahun 2008")
    assert r["PMK 92 Tahun 2005"][1] == "eksplisit" and r["PMK 83 Tahun 2007"][1] == "tersirat"


def test_new_fully_named_item_stays_direct_target():
    r = _relasi("Pasal 7 Pada saat Peraturan ini mulai berlaku, a. Peraturan Menteri Keuangan Nomor 10/PMK.03/2010 "
             "sebagaimana telah diubah dengan Peraturan Menteri Keuangan Nomor 20/PMK.03/2011; dan b. Peraturan "
             "Menteri Keuangan Nomor 30/PMK.03/2012, dicabut dan dinyatakan tidak berlaku.", "PMK 5 Tahun 2015")
    assert r["PMK 20 Tahun 2011"][1] == "tersirat" and r["PMK 30 Tahun 2012"] == ("mencabut", "eksplisit")


def test_sepanjang_mengatur_partial_revocation_and_nested_title_not_target():
    r = _relasi("Pasal 100 Pada saat Peraturan Menteri Keuangan ini mulai berlaku: 1. Peraturan Menteri Keuangan Nomor "
             "206/PMK.01/2014 tentang Organisasi dan Tata Kerja Kementerian Keuangan sepanjang yang mengatur mengenai "
             "Sekolah Tinggi Akuntansi Negara; dan 2. Peraturan Pemerintah Nomor 17 Tahun 2013 tentang Pelaksanaan "
             "Undang-Undang Nomor 20 Tahun 2008 tentang Usaha Mikro, dicabut dan dinyatakan tidak berlaku.",
             "PMK 2 Tahun 2016")
    assert r["PMK 206 Tahun 2014"][0] == "mencabut_sebagian"
    assert r["PP 17 Tahun 2013"] == ("mencabut", "eksplisit") and "UU 20 Tahun 2008" not in r


def test_keppres_recognised_and_its_amender_implied():
    r = _relasi("Pasal I Beberapa ketentuan dalam Keputusan Presiden Nomor 80 Tahun 2003 tentang Pedoman Pelaksanaan "
                "Pengadaan Barang/Jasa Pemerintah sebagaimana telah beberapa kali diubah terakhir dengan Peraturan "
                "Presiden Nomor 79 Tahun 2006, diubah sebagai berikut:", "PERPRES 85 Tahun 2006")
    assert r["KEPPRES 80 Tahun 2003"] == ("mengubah", "eksplisit")
    assert r["PERPRES 79 Tahun 2006"] == ("mengubah", "tersirat")


def test_provision_in_partially_revoked_regulation_with_own_heading_stays_target():
    r = _relasi("Pasal 50 Pada saat Peraturan Menteri ini mulai berlaku, ketentuan mengenai Dana Otonomi Khusus dalam "
                "Peraturan Menteri Keuangan Nomor 112/PMK.07/2016 tentang Pelaksanaan Pemantauan, dicabut dan "
                "dinyatakan tidak berlaku.", "PMK 76 Tahun 2022")
    assert r["PMK 112 Tahun 2016"][0] == "mencabut_sebagian"
    r = _relasi("Pasal 9 Peraturan Pemerintah Nomor 26 Tahun 1965 tentang Apotik sebagaimana telah diubah dengan "
                "Peraturan Pemerintah Nomor 25 Tahun 1980 (Lembaran Negara Tahun 1980 Nomor 40) dan Peraturan Pemerintah "
                "Nomor 41 Tahun 1990 tentang Masa Bakti Apoteker, dicabut dan dinyatakan tidak berlaku.",
                "PP 51 Tahun 2009")
    assert r["PP 25 Tahun 1980"][1] == "tersirat" and r["PP 41 Tahun 1990"] == ("mencabut", "eksplisit")


def test_spaced_item_marker_not_sentence_end():
    r = _relasi("Pasal 5 Dengan berlakunya Keputusan ini: a. Keputusan Menteri Keuangan Nomor 1061/KMK.00/1988 tentang "
                "Pendirian Bank; b. Keputusan Menteri Keuangan Nomor 1062/KMK.00/1988 tentang Pembukaan Kantor; E . "
                "Keputusan Menteri Keuangan Nomor 1055A/KMK.00/1989 tentang Perubahan atas Keputusan Menteri Keuangan "
                "Nomor 1062/KMK.00/1988; dinyatakan tidak berlaku lagi.", "KMK 220/KMK017/1993")
    assert r["KMK 1062/KMK00/1988"] == ("mencabut", "eksplisit")


def test_active_amends_and_amended_articles():
    rel, _ = find_relations(NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN MENTERI KEUANGAN TENTANG PERUBAHAN. Pasal I Mengubah beberapa ketentuan "
        "dalam Keputusan Menteri Keuangan Nomor 447/KMK.03/2002, sebagai berikut: 1. Ketentuan Pasal 1 diubah, "
        "sehingga keseluruhan Pasal 1 berbunyi sebagai berikut: Pasal 1 Batas penghasilan. 2. Ketentuan Pasal 2 "
        "diubah, sehingga berbunyi: Pasal 2 Cukup jelas. Pasal II Peraturan ini mulai berlaku."), "PMK 10 Tahun 2005")
    r = {x["ke"]: x for x in rel}
    assert r["KMK 447/KMK03/2002"]["jenis"] == "mengubah" and r["KMK 447/KMK03/2002"]["kelas"] == "eksplisit"
    assert r["KMK 447/KMK03/2002"]["pasal_terdampak"] == ["1", "2"]


def test_amended_articles_from_omnibus_instruction_items():
    rel, _ = find_relations(NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: UNDANG-UNDANG TENTANG HARMONISASI. Pasal 3 Beberapa ketentuan dalam Undang-Undang "
        "Nomor 7 Tahun 1983 tentang Pajak Penghasilan sebagaimana telah beberapa kali diubah terakhir dengan "
        "Undang-Undang Nomor 36 Tahun 2008 tentang Perubahan Keempat, diubah sebagai berikut: 1. Ketentuan ayat (1) "
        "dan ayat (3) Pasal 4 diubah sehingga berbunyi: Pasal 4 isi. 2. Ketentuan Pasal 8A ayat (2) dihapus. 3. Di "
        "antara Pasal 32B dan Pasal 33 disisipkan 1 (satu) pasal, yakni Pasal 32C sehingga berbunyi: Pasal 32C isi. "
        "Pasal 4 Beberapa ketentuan dalam Undang-Undang Nomor 8 Tahun 1983 diubah sebagai berikut: 1. Ketentuan "
        "Pasal 7 diubah."), "UU 7 Tahun 2021")
    r = {(x["ke"], x["kelas"]): x for x in rel}
    assert r[("UU 7 Tahun 1983", "eksplisit")]["pasal_terdampak"] == ["4", "8A", "32C"]
    assert r[("UU 36 Tahun 2008", "tersirat")]["pasal_terdampak"] is None
    assert r[("UU 8 Tahun 1983", "eksplisit")]["pasal_terdampak"] == ["7"]


def test_active_amends_first_mention_only_except_history():
    rel, _ = find_relations(NormText.from_raw(
        "MEMUTUSKAN: Menetapkan: PERATURAN MENTERI KEUANGAN. Pasal I Mengubah ketentuan Pasal 7 ayat (1) Peraturan "
        "Menteri Keuangan Nomor 66/PMK.03/2008 tentang Tata Cara Penyampaian Surat Pemberitahuan sebagaimana diatur "
        "dalam Undang-Undang Nomor 6 Tahun 1983 tentang Ketentuan Umum, sehingga berbunyi: Pasal 7 isi."),
        "PMK 12 Tahun 2009")
    assert {(x["ke"], x["kelas"]) for x in rel} == {("PMK 66 Tahun 2008", "eksplisit")}
