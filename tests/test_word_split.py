from __future__ import annotations

from taxagent.corpus.word_split import Lexicon, split_text, split_word

BERSIH = ("bahwa berdasarkan pertimbangan tersebut pajak penghasilan dikenakan atas penghasilan pegawai. "
          "peraturan menteri keuangan tentang pajak penghasilan. dari pemerintah daerah. di kantor pelayanan pajak. "
          "pertanggungjawaban dilaksanakan sesuai ketentuan. ") * 30
K = Lexicon.from_texts([BERSIH])


def test_joined_words_split():
    assert split_word("bahwaberdasarkan", K) == ["bahwa", "berdasarkan"]
    assert split_word("pajakpenghasilan", K) == ["pajak", "penghasilan"]
    assert split_word("dikantor", K) == ["di", "kantor"]


def test_valid_and_foreign_words_left_alone():
    assert split_word("pertanggungjawaban", K) is None
    assert split_word("dikenakan", K) is None
    assert split_word("andriansyah", K) is None
    assert split_word("pajak", K) is None


def test_pairs_never_seen_apart_left_alone():
    assert split_word("keuanganpajak", K) is None


def test_split_text_keeps_capitals_and_other_text():
    teks, n = split_text("Menimbang: BAHWABERDASARKAN Pasal 5, pajakPenghasilan 2o22 NIP19590420", K)
    assert teks == "Menimbang: BAHWA BERDASARKAN Pasal 5, pajak Penghasilan 2o22 NIP19590420"
    assert n == 2


def test_save_load(tmp_path):
    K.save(tmp_path / "k.json")
    assert Lexicon.load(tmp_path / "k.json").freq == K.freq
