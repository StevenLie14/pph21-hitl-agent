from taxagent.corpus.quality import noise
from taxagent.monitor.relation_llm import amendment_instructions, extract_relations, fold, verify

TEKS = (
    "MENIMBANG: bahwa Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian Besarnya "
    "Penghasilan Tidak Kena Pajak perlu disesuaikan. Pasal 1 Besarnya PTKP ... Pasal 4 Pada saat Peraturan "
    "Menteri ini mulai berlaku, Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian Besarnya "
    "Penghasilan Tidak Kena Pajak, dicabut dan dinyatakan tidak berlaku. Status Peraturan Dicabut"
)
BENAR = {"jenis": "mencabut", "jenis_peraturan": "PMK", "nomor": "122", "tahun": "2015",
         "kutipan": "Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian Besarnya Penghasilan Tidak Kena Pajak"}


def test_fold_tolerates_ocr_errors():
    assert fold("Nomor 1O/PMK.03/2O05") == fold("nomor 10/pmk.03/2005")
    assert fold("pemerintah") == fold("pemerin tah") and fold("rnenteri") == fold("menteri")


def test_verify_relation_correct_even_if_title_appears_twice():
    r, alasan = verify(BENAR, TEKS, ("PMK", 101, 2016))
    assert r is not None and r.kunci == ("mencabut", "PMK", 122, 2015), alasan


def test_verify_rejects_made_up_wrong_number_and_self():
    assert verify({**BENAR, "kutipan": "PMK 122 tahun 2015 dicabut seluruhnya oleh menteri"}, TEKS, None)[0] is None
    assert verify({**BENAR, "nomor": "123"}, TEKS, None)[0] is None
    assert verify({**BENAR, "jenis_peraturan": "PP"}, TEKS, None)[0] is None
    assert verify(BENAR, TEKS, ("PMK", 122, 2015))[0] is None


def test_verify_relation_verb_must_be_near_quote():
    teks = "Pasal 3 Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian Besarnya PTKP tetap berlaku."
    b = {**BENAR, "kutipan": "Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian Besarnya PTKP"}
    assert verify(b, teks, None)[0] is None
    assert verify({**b, "jenis": "mengubah"}, teks, None)[0] is None


class Klien:
    def __init__(self, dokumen, pasal=None):
        self.dokumen, self.pasal, self.panggilan = dokumen, pasal or [], 0

    def __call__(self, sistem, pengguna, versi):
        self.panggilan += 1
        if "Instruksi perubahan" in pengguna:
            return {"pasal": self.pasal}, {}
        return {"relasi": self.dokumen}, {}


UBAH = (
    "Pasal I Beberapa ketentuan dalam Keputusan Menteri Keuangan Nomor 447/KMK.03/2002 tentang Bagian Penghasilan "
    "diubah sebagai berikut: 1. Ketentuan Pasal 1 diubah, sehingga keseluruhan Pasal 1 berbunyi: Pasal 1 batas. "
    "2. Di antara Pasal 2 dan Pasal 3 disisipkan 1 (satu) pasal, yakni Pasal 2A sehingga berbunyi: Pasal 2A isi. "
    "Pasal II Peraturan ini mulai berlaku."
)


def test_extract_relations_with_articles_and_drops():
    dok = [{"jenis": "mengubah", "jenis_peraturan": "KMK", "nomor": "447", "tahun": "2002",
            "kutipan": "Beberapa ketentuan dalam Keputusan Menteri Keuangan Nomor 447/KMK.03/2002 tentang Bagian Penghasilan"},
           {"jenis": "mencabut", "jenis_peraturan": "PMK", "nomor": "9", "tahun": "2001", "kutipan": "karangan saja tanpa dasar"}]
    pasal = [{"nomor": "1", "kutipan": "Ketentuan Pasal 1 diubah, sehingga keseluruhan Pasal 1"},
             {"nomor": "2A", "kutipan": "disisipkan 1 (satu) pasal, yakni Pasal 2A sehingga"},
             {"nomor": "3", "kutipan": "pasal yang tidak ada di teks"}]
    h = extract_relations(UBAH, Klien(dok, pasal), ("PMK", 10, 2005))
    assert [(r.target, r.pasal) for r in h.relasi] == [("KMK 447/2002", ["1", "2A"])]
    assert len(h.dibuang) == 2 and len(h.mentah) == 2


def test_instruction_region_not_cut_by_same_target_title():
    from taxagent.monitor.relation_llm import Relation

    teks = "PERUBAHAN KEPUTUSAN MENTERI KEUANGAN NOMOR 447/KMK.03/2002. Mengubah beberapa ketentuan dalam " + UBAH
    r = Relation("mengubah", "KMK", 447, 2002, "PERUBAHAN KEPUTUSAN MENTERI KEUANGAN NOMOR 447/KMK.03/2002")
    ins, wilayah = amendment_instructions(teks, r)
    assert "Pasal 2A sehingga" in ins and "Pasal II" in wilayah


def test_noise_deterministic_and_damaging():
    t = "Peraturan Menteri Keuangan Nomor 122/PMK.010/2015 tentang Penyesuaian " * 20
    assert noise(t, 0.1, seed=3) == noise(t, 0.1, seed=3) != t
    assert noise(t, 0.0) == t


def test_full_regulation_style_number_accepted():
    from taxagent.monitor.relation_llm import int_number
    assert int_number("167/PMK.03/2018") == 167 and int_number("PER-16/PJ/2016") == 16 and int_number(" 058 ") == 58
    assert int_number("abc") is None


def test_verify_ignores_list_markers_from_two_column_ocr():
    teks = ("Pada saat Peraturan Menteri ini mulai berlaku:\nPeraturan Menteri Keuangan Nomor 250/PMK.03/2008\na.\n"
            "tentang Besarnya Biaya Jabatan atau Biaya Pensiun;\ndicabut dan dinyatakan tidak berlaku.")
    b = {"jenis": "mencabut", "jenis_peraturan": "PMK", "nomor": "250", "tahun": "2008",
         "kutipan": "Peraturan Menteri Keuangan Nomor 250/PMK.03/2008 tentang Besarnya Biaya Jabatan atau Biaya Pensiun;"}
    r, alasan = verify(b, teks, ("PMK", 168, 2023))
    assert r is not None, alasan
    b2 = dict(b, kutipan="Peraturan Menteri Keuangan Nomor 250/PMK.03/2008 tentang Besarnya Biaya Pegawai Harian;")
    assert verify(b2, teks, ("PMK", 168, 2023))[0] is None


def test_regulation_kind_must_point_to_target_number():
    from taxagent.monitor.relation_llm import _type_near_number

    assert not _type_near_number("Pada saat Peraturan Pemerintah ini mulai berlaku, Peraturan Menteri Pekerjaan Umum "
                                 "dan Perumahan Rakyat Nomor 11/PRT/M/2019 tentang Sistem, dicabut", "PP", 11)
    assert _type_near_number("Peraturan Pemerintah Nomor 73 tahun 2008 tentang Jenis dan Tarif dicabut", "PP", 73)
    assert _type_near_number("Peraturan Direktur Jenderal Pajak Nomor PER-67/PJ./2009 tentang Tata Cara", "PER", 67)


def test_kind_near_number_tolerates_ocr_spaces():
    from taxagent.monitor.relation_llm import _type_near_number

    assert _type_near_number("Peraturan MenteriKeuangan Nomor36/PMK.02/2013 tentang Tata Cara, dicabut", "PMK", 36)
    assert _type_near_number("Peraturan Menteri Keuangan Nomor 12 1/PMK.05/20 16 tentang Tata Cara", "PMK", 121)
