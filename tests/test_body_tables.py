from taxagent.update.body_tables import _find_page, rebuild_page, reflow
from taxagent.update.extraction import extract_amounts


def box(x0, y0, x1, text):
    return {"teks": text, "skor": 0.99, "x0": x0, "y0": y0, "x1": x1, "y1": y0 + 55}


PAGE = {"nomor": 56, "lebar": 2550, "tinggi": 3897, "kotak": [
    box(1158, 690, 1416, "PRESIDEN"),
    box(1013, 751, 1558, "REPUBLIK INDONESIA"),
    box(1173, 960, 1386, "Pasal 17"),
    box(796, 1062, 2239, "(1) Tarif pajak yang diterapkan atas Penghasilan Kena"),
    box(917, 1125, 1194, "Pajak bagi:"),
    box(1034, 1209, 2236, "Wajib Pajak orang pribadi dalam negeri sebagai"),
    box(918, 1219, 969, "a."),
    box(1038, 1271, 1235, "berikut:"),
    box(1124, 1366, 1636, "Lapisan Penghasilan"),
    box(1835, 1371, 2106, "Tarif Pajak"),
    box(1238, 1429, 1521, "Kena Pajak"),
    box(1058, 1510, 1246, "sampai"),
    box(1513, 1512, 1701, "dengan"),
    box(1928, 1513, 2015, "5%"),
    box(1059, 1568, 1494, "Rp60.000.000,00"),
    box(1538, 1573, 1703, "(enam"),
    box(1813, 1574, 2131, "(lima persen)"),
    box(1061, 1634, 1518, "puluh juta rupiah)"),
    box(1058, 1713, 1700, "di atas Rp60.000.000,00"),
    box(1917, 1717, 2031, "15%"),
    box(1060, 1776, 1699, "(enam puluh juta rupiah)"),
    box(1840, 1778, 2108, "(lima belas"),
    box(1059, 1836, 1246, "sampai"),
    box(1512, 1836, 1703, "dengan"),
    box(1877, 1838, 2064, "persen)"),
    box(1059, 1888, 1526, "Rp250.000.000,00"),
    box(1574, 1895, 1704, "(dua"),
    box(1057, 1949, 1705, "ratus lima puluh juta"),
    box(1059, 2011, 1246, "rupiah)"),
    box(1063, 2799, 1237, "di atas"),
    box(1916, 2800, 2034, "35%"),
    box(1061, 2854, 1571, "Rp250.000.000,00"),
    box(1779, 2858, 2174, "(tiga puluh lima"),
    box(1065, 2917, 1542, "(dua ratus lima puluh juta rupiah)"),
    box(1881, 2920, 2068, "persen)"),
    box(921, 3001, 978, "b."),
    box(1041, 3000, 2242, "Wajib Pajak badan dalam negeri dan bentuk"),
    box(182, 3760, 568, "SK No 115558 A"),
]}

PLAIN = "\n".join(k["teks"] for k in sorted(PAGE["kotak"], key=lambda k: (k["y0"], k["x0"])))


def test_rebuild_writes_one_row_per_line():
    new, note = rebuild_page(PAGE)
    assert note == "tabel 3 baris"
    lines = new.split("\n")
    assert "a. Wajib Pajak orang pribadi dalam negeri sebagai" in lines
    assert "Lapisan Penghasilan Kena Pajak Tarif Pajak" in lines
    assert "sampai dengan Rp60.000.000,00 (enam puluh juta rupiah) 5% (lima persen)" in lines
    assert ("di atas Rp60.000.000,00 (enam puluh juta rupiah) sampai dengan Rp250.000.000,00 (dua ratus lima puluh "
            "juta rupiah) 15% (lima belas persen)") in lines
    assert "di atas Rp250.000.000,00 (dua ratus lima puluh juta rupiah) 35% (tiga puluh lima persen)" in lines
    assert lines.index("b. Wajib Pajak badan dalam negeri dan bentuk") > lines.index("Lapisan Penghasilan Kena Pajak Tarif Pajak")


def test_pattern_extractor_reads_the_rebuilt_table_only():
    before = [f.key for f in extract_amounts(PLAIN, "s").findings]
    assert "tarif_pasal_17" not in before
    r = reflow("awal\n" + PLAIN + "\nakhir", b"", page_texts=[PLAIN], ocr=lambda content, pages: ({"halaman": [PAGE]}, None))
    assert r.pages == [56]
    assert r.text.startswith("awal\n") and r.text.endswith("\nakhir")
    rows = {f.key: f.value for f in extract_amounts(r.text, "s").findings}["tarif_pasal_17"]
    assert rows == [{"batas_atas": 60000000, "persen": 5}, {"batas_atas": 250000000, "persen": 15},
                    {"batas_atas": None, "persen": 35}]


def test_page_found_once_despite_repeated_headers():
    previous = "PRESIDEN\nREPUBLIK INDONESIA\nhalaman sebelumnya\nSK No 115557 A"
    following = "PRESIDEN\nREPUBLIK INDONESIA\nhalaman berikutnya"
    lines = (previous + "\n" + PLAIN + "\n" + following).split("\n")
    a, b = _find_page(lines, PAGE["kotak"])
    assert lines[a] == "PRESIDEN" and lines[a + 2] == "Pasal 17" and lines[b - 1] == "SK No 115558 A"


def test_other_reading_is_left_unchanged():
    other = PLAIN.replace("Rp250.000.000,00", "Rp250.000.000.00", 1)
    r = reflow(other, b"", page_texts=[other], ocr=lambda content, pages: ({"halaman": [PAGE]}, None))
    assert r.text == other and r.pages == []
    assert "tidak ditemukan tepat sekali" in r.lines[0]


def test_page_without_table_end_is_not_rebuilt():
    page = {**PAGE, "kotak": [k for k in PAGE["kotak"] if k["y0"] < 3000]}
    assert rebuild_page(page) == (None, "akhir tabel tidak terlihat")


def test_ocr_failure_keeps_the_text():
    r = reflow(PLAIN, b"", page_texts=[PLAIN], ocr=lambda content, pages: (None, "exit 1"))
    assert r.text == PLAIN and r.lines[0].startswith("PERINGATAN")
