from __future__ import annotations

import json
from decimal import Decimal

from taxagent.taxes.pph21.calc.rates import load_raw
from taxagent.update import assemble_draft
from taxagent.update.amounts import format_rupiah, to_terbilang
from taxagent.update.assemble import Draft, compare
from taxagent.update.extraction import ExtractionResult, Finding
from taxagent.update.gates import GateContext, GateResult
from taxagent.update.llm import GROUPS, leaves
from taxagent.update.ter_table import (
    Row,
    TableResult,
    _column_bounds,
    check_structure,
    findings_from,
    ocr_boxes,
    read_columns,
    read_with_vision,
    yaml_values,
)

LEBAR = 2500


def _rp(n: int) -> str:
    return f"{format_rupiah(n)} ({to_terbilang(n)} rupiah)"


def _pct(p: str) -> list[str]:
    return [f"{p}%", f"({to_terbilang(Decimal(p.replace(',', '.')))} persen)"]


def _halaman(nomor: int, judul: str | None, baris: list[tuple[int | None, int | None, str]], y: int = 1000,
             salah_terbilang: int | None = None) -> dict:
    kotak = [{"teks": "PRESIDEN", "x0": 1100, "y0": 300, "x1": 1400, "y1": 350}]
    if judul:
        kotak.append({"teks": judul, "x0": 280, "y0": y - 200, "x1": 1400, "y1": y - 150})
        kotak.append({"teks": "Tarif Pajak", "x0": 1800, "y0": y - 100, "x1": 2080, "y1": y - 50})
    for bawah, atas, p in baris:
        kiri = []
        if bawah is not None:
            kiri.append(f"di atas {_rp(bawah)}")
        if atas is not None:
            teks_atas = _rp(atas)
            if salah_terbilang == atas:
                teks_atas = f"{format_rupiah(atas)} ({to_terbilang(atas + 1000)} rupiah)"
            kiri.append(("sampaidengan " if bawah is not None else "sampai dengan ") + teks_atas)
        potong = " ".join(kiri).split(" (")
        kiri_baris = [potong[0]] + ["(" + x for x in potong[1:]]
        kanan = _pct(p)
        for i in range(max(len(kiri_baris), len(kanan))):
            if i < len(kiri_baris):
                kotak.append({"teks": kiri_baris[i], "x0": 430, "y0": y, "x1": 1660, "y1": y + 50})
            if i < len(kanan):
                kotak.append({"teks": kanan[i], "x0": 1750 + 10 * i, "y0": y + 20, "x1": 2100, "y1": y + 70})
            y += 60
        y += 40
    kotak.append({"teks": "SK No 190042 A", "x0": 170, "y0": 3790, "x1": 560, "y1": 3840})
    return {"nomor": nomor, "lebar": LEBAR, "tinggi": 3900, "kotak": kotak}


A = [(None, 5400000, "0"), (5400000, 5650000, "0,25"), (5650000, None, "0,5")]
B = [(None, 6200000, "0"), (6200000, None, "1")]
HARIAN = [(None, 450000, "0"), (450000, 2500000, "0,5")]


def _data(**ubah) -> dict:
    return {"halaman": [
        _halaman(11, "A. TARIF EFEKTIF BULANAN KATEGORI A", ubah.get("a", A)[:2]),
        _halaman(12, None, ubah.get("a", A)[2:], **ubah.get("kw12", {})),
        _halaman(13, "B. TARIF EFEKTIF BULANAN KATEGORI B", ubah.get("b", B)),
        _halaman(14, "D. TARIF EFEKTIF HARIAN", HARIAN),
    ]}


def test_table_structure():
    ok = [Row(None, Decimal(10), Decimal(0)), Row(Decimal(10), Decimal(20), Decimal(1)), Row(Decimal(20), None, Decimal(2))]
    assert check_structure(ok) == []
    celah = [ok[0], Row(Decimal(11), Decimal(20), Decimal(1)), ok[2]]
    assert "batas bawah 11 != batas atas baris sebelumnya 10" in check_structure(celah)[0]
    turun = [ok[0], Row(Decimal(10), Decimal(20), Decimal(3)), ok[2]]
    assert any("turun" in x for x in check_structure(turun))
    terbuka = [ok[0], Row(Decimal(10), None, Decimal(1)), ok[2]]
    assert any("terbuka" in x for x in check_structure(terbuka))
    assert check_structure([]) == ["tidak ada baris"]


def test_column_gap_from_coordinates():
    b = _column_bounds(_halaman(11, "A. TARIF EFEKTIF BULANAN KATEGORI A", A))
    assert 1660 < b < 1750


def test_ocr_extractor_splits_columns_and_checks_words():
    h = read_columns(_data())
    assert h.title == ["A", "B", "harian"]
    assert h.notes == [] and h.mismatches == []
    nilai = yaml_values(h.table)
    assert nilai["ter_bulanan"]["A"] == [{"batas_atas": 5400000, "persen": 0}, {"batas_atas": 5650000, "persen": 0.25},
                                         {"batas_atas": None, "persen": 0.5}]
    assert nilai["ter_bulanan"]["B"][-1] == {"batas_atas": None, "persen": 1}
    assert nilai["ter_harian"] == {"lapisan": [{"batas_atas": 450000, "persen": 0}, {"batas_atas": 2500000, "persen": 0.5}]}
    assert {Decimal(5650000), Decimal("0.25")} <= h.verified


def test_mismatched_number_words_reported():
    h = read_columns(_data(kw12={"salah_terbilang": None}, a=[(None, 5400000, "0"), (5400000, 5650000, "0,25"),
                                                              (5650000, 5950000, "0,5"), (5950000, None, "1")]))
    assert h.mismatches == []
    data = _data()
    data["halaman"][0] = _halaman(11, "A. TARIF EFEKTIF BULANAN KATEGORI A", A[:2], salah_terbilang=5650000)
    h = read_columns(data)
    assert any("5.650.000" in x for x in h.mismatches)


def test_category_damaged_all_or_nothing():
    rusak = [(None, 6200000, "0"), (6300000, None, "1")]
    h = read_columns(_data(b=rusak))
    assert "A" not in h.table and "B" not in h.table and "harian" in h.table
    assert any("ter_bulanan tidak dipakai" in c for c in h.notes)
    e = findings_from(h, "pp.pdf")
    assert [t.key for t in e.findings] == ["ter_harian"]


class VisiPalsu:
    def __init__(self, per_halaman: list[list[dict]]):
        self.per_halaman, self.n = per_halaman, 0

    def __call__(self, sistem, png, versi):
        b = self.per_halaman[self.n]
        self.n += 1
        return {"baris": b}, {"token_masuk": 10, "token_keluar": 5}


def _visi(baris_a_akhir: dict) -> VisiPalsu:
    return VisiPalsu([
        [{"judul": "A. TARIF EFEKTIF BULANAN KATEGORI A", "batas_bawah": None, "batas_atas": 5400000, "persen": 0},
         {"judul": None, "batas_bawah": 5400000, "batas_atas": 5650000, "persen": 0.25}],
        [baris_a_akhir],
        [{"judul": "B. TARIF EFEKTIF BULANAN KATEGORI B", "batas_bawah": None, "batas_atas": 6200000, "persen": 0},
         {"judul": None, "batas_bawah": 6200000, "batas_atas": None, "persen": 1}],
    ])


def test_vision_extractor_carries_category_and_leaf_path():
    h, llm = read_with_vision([(1, b""), (2, b""), (3, b"")],
                              _visi({"judul": None, "batas_bawah": 5650000, "batas_atas": None, "persen": 0.5}))
    assert llm.valid and h.notes == []
    assert llm.values["ter_bulanan.A[1].batas_atas"] == Decimal(5650000)
    assert llm.values["ter_bulanan.A[2].batas_atas"] is None
    assert llm.values["ter_bulanan.B[1].persen"] == Decimal(1)


def test_vision_extractor_misread_lower_bound_rejected():
    h, llm = read_with_vision([(1, b""), (2, b""), (3, b"")],
                              _visi({"judul": None, "batas_bawah": 565000, "batas_atas": None, "persen": 0.5}))
    assert "A" not in h.table and not any(j.startswith("ter_bulanan") for j in llm.values)
    assert any("kategori A" in x for x in llm.dropped)


def _tabel_2024(ubah: tuple[str, int, str, object] | None = None) -> TableResult:
    t = load_raw(2024)["ter_bulanan"]
    h = TableResult(title=list(t))
    for k, rows in t.items():
        bs, bawah = [], None
        for r in rows:
            atas = None if r["batas_atas"] is None else Decimal(r["batas_atas"])
            bs.append(Row(bawah, atas, Decimal(str(r["persen"]))))
            bawah = atas
        h.table[k] = bs
        h.quote[k] = " ".join(f"RP{b.upper} {b.percent}%" for b in bs)
        h.verified |= {b.upper for b in bs if b.upper is not None} | {b.percent for b in bs}
    if ubah:
        k, i, f, v = ubah
        setattr(h.table[k][i], f, Decimal(str(v)))
        if f == "upper":
            h.table[k][i + 1].lower = Decimal(str(v))
        h.quote[k] += f" {v}%"
        h.verified.add(Decimal(str(v)))
    return h


def _llm_dari(h: TableResult):
    from taxagent.update.llm import LLMResult

    llm = LLMResult(group=["ter_bulanan"])
    for key, v in yaml_values(h.table).items():
        leaves(v, key, llm.values)
    return llm


def _gerbang(d: Draft) -> dict[str, GateResult]:
    return {g.code: g for g in d.gates}


def test_changed_ter_draft_passes_g2_g3_g4_when_both_extractors_agree():
    h = _tabel_2024(("A", 5, "percent", "1.3"))
    d = assemble_draft(2027, [findings_from(h, "pp_baru.pdf")], 2026, GateContext(phase1_keys=["ter_bulanan"], llm=_llm_dari(h)))
    p = next(x for x in d.comparisons if x.key == "ter_bulanan")
    assert p.status == "berubah" and p.new["A"][5]["persen"] == 1.3
    g = _gerbang(d)
    assert g["G1"].passed and g["G2"].passed and g["G3"].passed and g["G4"].passed and g["G5"].passed, \
        [(k, x.reasons) for k, x in g.items()]
    assert "ter_bulanan:" in d.yaml_text


def test_ter_draft_one_cell_differing_between_extractors_held_g4():
    h = _tabel_2024(("A", 5, "percent", "1.3"))
    llm = _llm_dari(h)
    llm.values["ter_bulanan.C[4].batas_atas"] = Decimal(8500000)
    d = assemble_draft(2027, [findings_from(h, "pp_baru.pdf")], 2026, GateContext(phase1_keys=["ter_bulanan"], llm=llm))
    g4 = _gerbang(d)["G4"]
    assert g4.passed is False and any("C[4].batas_atas: deterministik 8850000, LLM 8500000" in a for a in g4.reasons)
    assert d.decision == "tahan"


def test_ter_draft_without_words_held_g3():
    h = _tabel_2024(("B", 3, "percent", "0.8"))
    h.verified.discard(Decimal("0.8"))
    d = assemble_draft(2027, [findings_from(h, "pp_baru.pdf")], 2026, GateContext(llm=_llm_dari(h)))
    assert _gerbang(d)["G3"].passed is False


def test_daily_ter_two_extractors_one_source_merged_not_conflict():
    teks = ExtractionResult(findings=[Finding("ter_harian", {"batas_bebas_harian": 450000}, "kutip", "pp.pdf")])
    tabel = ExtractionResult(findings=[Finding("ter_harian", {"lapisan": [{"batas_atas": 450000, "persen": 0},
                                                                        {"batas_atas": 2500000, "persen": 0.5}]},
                                             "tabel", "pp.pdf")])
    p = next(x for x in compare([teks, tabel], load_raw(2024)) if x.key == "ter_harian")
    assert p.status == "sama"


def test_monthly_ter_not_asked_of_text_llm():
    assert "ter_bulanan" not in GROUPS and "ter_harian" in GROUPS


def test_ocr_boxes_cached(tmp_path):
    panggilan = []

    def jalankan(cmd, **kw):
        panggilan.append(cmd)
        keluar = cmd[cmd.index("--pages") - 1]
        with open(keluar, "w", encoding="utf-8") as f:
            json.dump({"halaman": []}, f)

        class R:
            returncode, stdout, stderr = 0, "", ""
        return R()

    data, err = ocr_boxes(b"%PDF-1", [11, 12, 13, 15], cache=tmp_path, run=jalankan)
    assert err is None and data == {"halaman": []}
    assert "11-13,15" in panggilan[0]
    data, err = ocr_boxes(b"%PDF-1", [11, 12, 13, 15], cache=tmp_path, run=jalankan)
    assert len(panggilan) == 1


def test_read_table_reports_without_crashing(monkeypatch):
    import taxagent.update.ter_table as T

    monkeypatch.setattr(T, "table_pages", lambda content: [11, 12, 13, 14])
    monkeypatch.setattr(T, "ocr_boxes", lambda content, pages: (_data(b=[(None, 6200000, "0")]), None))
    r = T.read_table(b"%PDF", "PP 58 Tahun 2023")
    assert r.extraction is not None and r.llm is None
    assert r.lines[0].startswith("Tabel TER di lampiran: OCR kotak 4 halaman")
    assert any("OCR:" in x for x in r.lines)
