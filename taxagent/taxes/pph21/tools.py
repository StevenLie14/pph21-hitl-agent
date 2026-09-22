from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from ...tools.registry import DISCLAIMER
from ...tools.registry import error_result as _error
from ...tools.registry import result_basis_status as _basis_status
from ...tools.registry import result_locations as _locations
from . import tool_schemas as S
from .calc import (
    Article17DirectType,
    FinalIncomeType,
    IncomeComponents,
    PPh21Result,
    TaxYearNotAvailable,
    WageScheme,
    apply_ikn_facility,
    available_years,
    calc_annual,
    calc_article17_direct,
    calc_commissioner,
    calc_final,
    calc_final_period,
    calc_final_period_gross_up,
    calc_in_kind,
    calc_lump_sum_third_year,
    calc_monthly_ter,
    calc_monthly_ter_gross_up,
    calc_non_employee,
    calc_non_permanent_employee,
    calc_pensioner_annual,
    calc_pensioner_final_period,
    calc_pensioner_monthly_ter,
    calc_pph26,
    default_year,
    determine_object_code,
    format_rupiah,
    load_rates,
    load_regulations,
    money,
    object_code_info,
    parse_ptkp_status,
    ptkp_code,
)


def _today():
    import datetime

    return datetime.date.today()


def _missing_year_hint(year: int, available: list[int]) -> str:
    hint = f"Tahun yang tersedia: {available}."
    if not available or year <= max(available):
        return hint
    today = _today()
    if year > today.year:
        return hint + (f" Tahun pajak {year} belum berjalan (hari ini {today.isoformat()}); aturannya mungkin belum "
                       f"terbit, jadi ini bukan data usang: JANGAN panggil report_possibly_stale. Katakan kepada "
                       f"pengguna bahwa tahun itu belum bisa dihitung secara pasti. Bila pengguna butuh angka, boleh "
                       f"hitung dengan tahun_pajak {max(available)} dan sebut jelas di jawaban bahwa itu PERKIRAAN "
                       f"memakai aturan {max(available)} yang bisa berubah.")
    return hint + (f" Tahun ini lebih baru dari tabel yang ada: panggil report_possibly_stale dengan "
                   f"alasan tabel_tarif_belum_ada dan tanggal_fakta di tahun {year}.")


def _year(kw: dict) -> int:
    year = kw.get("tahun_pajak")
    return default_year() if year is None else year


def _number(value) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")) if value % 1 else value.to_integral_value())
    return value


def result_to_dict(h: PPh21Result) -> dict:
    return {
        "jenis_perhitungan": h.jenis_perhitungan,
        "tahun_pajak": h.tahun_pajak,
        "masa_pajak": h.masa_pajak,
        "metode_tarif": h.metode_tarif,
        "penghasilan_bruto": _number(h.penghasilan_bruto),
        "dasar_pengenaan_pajak": _number(h.dasar_pengenaan_pajak),
        "pph_sebelum_penalti": _number(h.pph_sebelum_penalti),
        "penalti_non_npwp": _number(h.penalti_non_npwp),
        "pph_terutang": _number(h.pph_terutang),
        "pph_terutang_terbaca": format_rupiah(h.pph_terutang),
        **({"pph_ditanggung_pemerintah": _number(h.pph_ditanggung_pemerintah),
            "pph_ditanggung_pemerintah_terbaca": format_rupiah(h.pph_ditanggung_pemerintah)}
           if h.pph_ditanggung_pemerintah else {}),
        "objek_pajak": object_code_info(h.kode_objek_pajak),
        "langkah": [
            {
                "label": l.label,
                "formula": l.formula,
                "nilai": _number(l.nilai),
                "nilai_terbaca": format_rupiah(l.nilai) if l.nilai is not None else None,
                "catatan": l.catatan,
            }
            for l in h.langkah
        ],
        "dasar_hukum": h.dasar_hukum,
        "asumsi": h.asumsi,
        "peringatan": h.peringatan,
        "disclaimer": DISCLAIMER,
    }


ANNUAL_TOOLS = {
    "calculate_pph21_permanent_annual", "calculate_pph21_permanent_last_period",
    "calculate_pph21_pensioner_annual", "calculate_pph21_pensioner_last_period",
}
MIN_MONTHLY_AVERAGE = Decimal(2_000_000)

_TOOL_KIND = {
    "calculate_pph21_permanent_monthly": "PPh 21 pegawai tetap, satu masa pajak (TER)",
    "calculate_pph21_permanent_annual": "PPh 21 pegawai tetap, setahun (Pasal 17)",
    "calculate_pph21_permanent_last_period": "PPh 21 pegawai tetap, masa pajak terakhir",
    "calculate_pph21_pensioner_monthly": "PPh 21 pensiunan, satu masa pajak (TER)",
    "calculate_pph21_pensioner_annual": "PPh 21 pensiunan, setahun (Pasal 17)",
    "calculate_pph21_pensioner_last_period": "PPh 21 pensiunan, masa pajak terakhir",
    "calculate_pph21_non_permanent": "PPh 21 pegawai tidak tetap",
    "calculate_pph21_non_employee": "PPh 21 bukan pegawai",
    "calculate_pph21_commissioner": "PPh 21 anggota dewan komisaris/pengawas",
    "calculate_pph21_final": "PPh 21 final",
    "calculate_pph21_direct_pasal_17": "PPh 21 tarif Pasal 17 langsung",
    "calculate_pph_pasal_26": "PPh Pasal 26",
}
_NOT_MONEY = {"tahun_pajak", "masa_pajak", "bulan_masa_perolehan", "jumlah_hari", "tarif_p3b_persen",
               "tahun_pembayaran_ke"}
_NOT_SCALED = {"pph_sudah_dipotong", "neto_pemberi_kerja_sebelumnya", "pph_dipotong_pemberi_kerja_sebelumnya",
                 "neto_pemberi_sebelumnya", "pph_dipotong_pemberi_sebelumnya"}
_FLAGS = {"gross_up": "PPh ditanggung perusahaan (gross-up)", "disetahunkan": "disetahunkan",
            "jasa_katering": "jasa katering", "ada_surat_keterangan_domisili": "ada SKD",
            "fasilitas_ikn": "fasilitas PPh 21 ditanggung pemerintah IKN"}
_MONTHS = ["", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September",
          "Oktober", "November", "Desember"]


def input_summary(name: str, kw: dict, result: dict) -> str:
    parts = [_TOOL_KIND.get(name, name)]
    year = kw.get("tahun_pajak") or result.get("tahun_pajak")
    period = kw.get("masa_pajak")
    if name in ANNUAL_TOOLS:
        n = kw.get("bulan_masa_perolehan", 12)
        parts.append(f"tahun pajak {year}, {n} bulan masa perolehan")
        if name.endswith("last_period") and period:
            parts.append(f"masa pajak terakhir {_MONTHS[int(period)]}")
    elif period:
        parts.append(f"masa pajak {_MONTHS[int(period)]} {year}")
    elif year:
        parts.append(f"tahun pajak {year}")
    if kw.get("status_ptkp"):
        parts.append(f"status {kw['status_ptkp']}")
    if "punya_npwp" in kw or "status_ptkp" in kw:
        parts.append("ber-NPWP" if kw.get("punya_npwp", True) else "tanpa NPWP")
    per_month = bool(kw.get("nilai_per_bulan")) and name in ANNUAL_TOOLS
    n = kw.get("bulan_masa_perolehan", 12)
    for k, v in kw.items():
        if k in _FLAGS:
            if v is True:
                parts.append(_FLAGS[k])
        elif isinstance(v, bool) or v is None or k in ("status_ptkp", "nilai_per_bulan", "punya_npwp",
                                                        "kutipan_status_ptkp"):
            continue
        elif isinstance(v, str):
            if v.strip():
                parts.append(f"{k.replace('_', ' ')}: {v}")
        elif k not in _NOT_MONEY and v:
            text = f"{k.replace('_', ' ')} {format_rupiah(money(v))}"
            if per_month and k not in _NOT_SCALED:
                text += f" per bulan x {n} bulan"
            parts.append(text)
        elif k == "jumlah_hari" and v:
            parts.append(f"{v} hari")
        elif k == "tahun_pembayaran_ke" and v and v >= 3:
            parts.append(f"dibayar pada tahun kalender ke-{v} (tidak final)")
    if result.get("penghasilan_bruto") is not None:
        parts.append(f"penghasilan bruto yang dihitung {format_rupiah(money(result['penghasilan_bruto']))}")
    return "; ".join(parts) + "."


def check_inputs(name: str, kw: dict, result: dict) -> list[str]:
    confirmations = []
    if name not in ANNUAL_TOOLS:
        return confirmations
    n = int(kw.get("bulan_masa_perolehan", 12) or 12)
    gross = money(result.get("penghasilan_bruto") or 0)
    if not kw.get("nilai_per_bulan") and n and gross and gross / n < MIN_MONTHLY_AVERAGE:
        confirmations.append(
            f"Penghasilan bruto {format_rupiah(gross)} diperlakukan sebagai TOTAL {n} bulan "
            f"(rata-rata {format_rupiah(gross / n)} sebulan). Bila pengguna menyebut angka itu sebagai "
            "jumlah SEBULAN, panggil ulang dengan nilai_per_bulan=true dan bulan_masa_perolehan yang sesuai."
        )
    if n < 12 and not kw.get("disetahunkan"):
        confirmations.append(
            f"Masa perolehan {n} bulan dengan disetahunkan=false: benar bila penerima hanya mulai/berhenti "
            "bekerja dan tetap tinggal di Indonesia. Bila kewajiban pajak subjektifnya baru mulai atau berakhir "
            "di tahun ini (WNA baru datang/menetap, meninggal, meninggalkan Indonesia selamanya), panggil ulang "
            "dengan disetahunkan=true."
        )
    if (name.endswith("last_period") and n > 1 and not kw.get("pph_sudah_dipotong")
            and not kw.get("pph_sudah_dipotong_ter_sama") and not kw.get("gross_up")):
        confirmations.append(
            "PPh 21 yang sudah dipotong pada masa-masa sebelumnya diisi Rp0, sehingga hasil masa pajak terakhir sama "
            "dengan PPh setahun penuh. Bila PPh sudah dipotong setiap bulan, hasilnya jauh lebih kecil: sebutkan "
            "jumlah di bukti potong" + (", atau minta diperkirakan dari TER bulanan."
                                         if name == "calculate_pph21_permanent_last_period" else ".")
        )
    return confirmations


_KEYS_USED = {
    "lookup_ptkp": ("ptkp",),
    "lookup_ter": ("kategori_ter", "ter_bulanan"),
    "lookup_pasal_17_rates": ("tarif_pasal_17",),
    "calculate_pph21_permanent_monthly": ("kategori_ter", "ter_bulanan"),
    "calculate_pph21_permanent_annual": ("biaya_jabatan", "ptkp", "tarif_pasal_17"),
    "calculate_pph21_permanent_last_period": ("biaya_jabatan", "ptkp", "tarif_pasal_17"),
    "calculate_pph21_pensioner_monthly": ("kategori_ter", "ter_bulanan"),
    "calculate_pph21_pensioner_annual": ("biaya_pensiun", "ptkp", "tarif_pasal_17"),
    "calculate_pph21_pensioner_last_period": ("biaya_pensiun", "ptkp", "tarif_pasal_17"),
}
HPP_FIRST_YEAR = 2022


def dated_basis(name: str, result: dict, kw: dict) -> None:
    from ...monitor.identity import find_all

    if os.environ.get("PPH21_ABLATION_SOURCES") == "0":
        return
    basis = result.get("dasar_hukum")
    year = result.get("tahun_pajak") or _year(kw)
    if not isinstance(basis, list) or not isinstance(year, int):
        return
    try:
        sources = load_rates(year).dasar_hukum_kunci
    except TaxYearNotAvailable:
        sources = {}
    used = {k: sources[k] for k in _KEYS_USED.get(name, ()) if sources.get(k)}
    kept = []
    for ref in basis:
        if year < HPP_FIRST_YEAR:
            ref = ref.replace(" s.t.d.t.d UU HPP", "")
        if any(i.year > year for i in find_all(ref.upper())):
            continue
        kept.append(ref)
    named = {i for ref in kept for i in find_all(ref.upper())}
    for x in dict.fromkeys(used.values()):
        ids = set(find_all(x.upper()))
        if not (ids and ids <= named) and x not in kept:
            kept.append(x)
            named |= ids
    result["dasar_hukum"] = kept
    if used:
        result["dasar_hukum_nilai"] = used


def _tool(fn: Callable[..., dict]) -> Callable[..., dict]:
    def wrapper(**kw):
        try:
            result = fn(**kw)
            if result.get("berhasil"):
                dated_basis(fn.__name__, result, kw)
            if result.get("berhasil") and (st := _basis_status(result, kw)) is not None:
                result["status_dasar_hukum"] = st
            if result.get("berhasil") and (locs := _locations(result.get("dasar_hukum") or result.get("rujukan"))):
                result["lokasi_dasar_hukum"] = locs
            if result.get("berhasil") and fn.__name__ in _TOOL_KIND:
                return {
                    "berhasil": True,
                    "perlu_konfirmasi": check_inputs(fn.__name__, kw, result),
                    "ringkasan_masukan": input_summary(fn.__name__, kw, result),
                    **{k: v for k, v in result.items() if k != "berhasil"},
                }
            return result
        except TaxYearNotAvailable as e:
            return _error(str(e), _missing_year_hint(_year(kw), available_years()))
        except (ValueError, LookupError) as e:
            return _error(str(e), "Perbaiki argumen lalu panggil ulang, atau tanyakan kepada pengguna.")
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _components(kw: dict) -> IncomeComponents:
    return IncomeComponents(
        gaji_pokok=kw.get("gaji_pokok", 0),
        tunjangan_tetap=kw.get("tunjangan_tetap", 0),
        tunjangan_tidak_tetap=kw.get("tunjangan_tidak_tetap", 0),
        lembur=kw.get("lembur", 0),
        bonus_thr_komisi=kw.get("bonus_thr_komisi", 0),
        tunjangan_pph=kw.get("tunjangan_pph", 0),
        premi_jkk_dibayar_pemberi_kerja=kw.get("premi_jkk_dibayar_perusahaan", 0),
        premi_jkm_dibayar_pemberi_kerja=kw.get("premi_jkm_dibayar_perusahaan", 0),
        premi_bpjs_kesehatan_dibayar_pemberi_kerja=kw.get("premi_bpjs_kesehatan_dibayar_perusahaan", 0),
        natura_kena_pajak=kw.get("natura_kena_pajak", 0),
        penghasilan_lain=kw.get("penghasilan_lain", 0),
        iuran_jht_dibayar_pemberi_kerja=kw.get("iuran_jht_dibayar_perusahaan", 0),
        iuran_jp_dibayar_pemberi_kerja=kw.get("iuran_jp_dibayar_perusahaan", 0),
        iuran_pensiun_dibayar_pegawai=kw.get("iuran_pensiun_dibayar_pegawai", 0),
        iuran_jht_dibayar_pegawai=kw.get("iuran_jht_dibayar_pegawai", 0),
        iuran_jp_dibayar_pegawai=kw.get("iuran_jp_dibayar_pegawai", 0),
        zakat_via_pemberi_kerja=kw.get("zakat_via_pemberi_kerja", 0),
        iuran_bpjs_kesehatan_dibayar_pegawai=kw.get("iuran_bpjs_kesehatan_dibayar_pegawai", 0),
    )


def _month_factor(kw: dict) -> tuple[int, str | None]:
    if not kw.get("nilai_per_bulan"):
        return 1, None
    n = int(kw.get("bulan_masa_perolehan", 12))
    return n, f"Nilai yang diisi adalah jumlah sebulan; tool mengalikannya dengan {n} bulan."


def _period_components(kw: dict) -> tuple[IncomeComponents, str | None]:
    n, note = _month_factor(kw)
    k = _components(kw)
    if k.bruto() == 0 and not kw.get("neto_pemberi_kerja_sebelumnya"):
        raise ValueError(
            "seluruh komponen penghasilan nol; isi gaji dan penghasilan dari pemberi kerja ini "
            "ke gaji_pokok dan komponen lain (nilai total, atau nilai sebulan dengan "
            "nilai_per_bulan=true)"
        )
    return (k.scaled(n) if n != 1 else k), note


def _choice(enum, text: str, name: str):
    try:
        return enum(text.strip().lower())
    except ValueError:
        raise ValueError(f"{name} '{text}' tidak dikenali; pilih " + ", ".join(x.value for x in enum)) from None


def _note(h: PPh21Result, note: str | None) -> PPh21Result:
    if note:
        h.asumsi.insert(0, note)
    return h


def _finish(h: PPh21Result, kw: dict, **code_kw) -> dict:
    ikn = bool(kw.get("fasilitas_ikn"))
    if ikn and kw.get("gross_up"):
        raise ValueError("fasilitas_ikn tidak digabung dengan gross_up: PPh 21 DTP IKN tidak dihitung sebagai "
                         "penghasilan pegawai, jadi tidak ada tunjangan PPh")
    h.kode_objek_pajak = determine_object_code(h, ikn=ikn, **code_kw)
    if ikn:
        apply_ikn_facility(h, kw.get("punya_npwp", True))
    if not h.kode_objek_pajak and h.jenis_perhitungan in ("bukan_pegawai", "pasal17_langsung_peserta_kegiatan"):
        h.asumsi.append("Kode objek pajak bukti potong bergantung pada jenis penerima, yang belum disebut.")
    return {"berhasil": True, **result_to_dict(h)}


@_tool
def lookup_ptkp(kawin: bool, jumlah_tanggungan: int, tahun_pajak: int | None = None,
                kutipan_status_ptkp: str = "") -> dict:
    tahun_pajak = default_year() if tahun_pajak is None else tahun_pajak
    status, peringatan = ptkp_code(kawin, jumlah_tanggungan, tahun_pajak)
    table = load_rates(tahun_pajak)
    return {
        "berhasil": True,
        "status_ptkp": status.value,
        "ptkp_setahun": _number(table.annual_ptkp(status)),
        "ptkp_setahun_terbaca": format_rupiah(table.annual_ptkp(status)),
        "kategori_ter": table.ter_category(status).value,
        "peringatan": peringatan + table.verification_warning(),
        "dasar_hukum": ["UU PPh Pasal 7 ayat (1)"],
    }


@_tool
def lookup_ter(status_ptkp: str, penghasilan_bruto_sebulan: float, tahun_pajak: int | None = None) -> dict:
    table = load_rates(tahun_pajak if tahun_pajak is not None else default_year())
    status = parse_ptkp_status(status_ptkp)
    category = table.ter_category(status)
    bracket = table.monthly_ter_rate(category, penghasilan_bruto_sebulan)
    return {
        "berhasil": True,
        "status_ptkp": status.value,
        "kategori_ter": category.value,
        "tarif_persen": _number(bracket.persen),
        "bracket_batas_atas": _number(bracket.batas_atas),
        "peringatan": table.verification_warning(),
        "dasar_hukum": ["PP No. 58 Tahun 2023"],
    }


@_tool
def lookup_pasal_17_rates(tahun_pajak: int | None = None) -> dict:
    table = load_rates(tahun_pajak if tahun_pajak is not None else default_year())
    return {
        "berhasil": True,
        "lapisan": [
            {"batas_atas": _number(l.batas_atas), "persen": _number(l.persen)}
            for l in table.tarif_pasal_17
        ],
        "peringatan": table.verification_warning(),
        "dasar_hukum": ["UU PPh Pasal 17 ayat (1) huruf a s.t.d.t.d UU HPP"],
    }


@_tool
def find_legal_basis(topic: str) -> dict:
    topics = load_regulations()
    key = topic.strip().lower().replace(" ", "_").replace("-", "_")
    if key in topics:
        return {"berhasil": True, "topik": key, **topics[key]}
    matches = [k for k in topics if key in k or k in key]
    if len(matches) == 1:
        return {"berhasil": True, "topik": matches[0], **topics[matches[0]]}
    return _error(
        f"Topik '{topic}' tidak ada dalam peta regulasi.",
        f"Topik yang tersedia: {', '.join(sorted(topics))}. "
        "Jangan mengarang rujukan pasal yang tidak ada di daftar ini.",
    )


@_tool
def calculate_taxable_natura(**kw) -> dict:
    args = {k: v for k, v in kw.items() if k not in ("tahun_pajak", "masa_pajak")}
    period = kw.get("masa_pajak") or None
    h = calc_in_kind(_year(kw), masa_pajak=period, **args)
    return {
        "berhasil": True,
        "natura_kena_pajak": _number(h.dasar_pengenaan_pajak),
        "total_natura": _number(h.penghasilan_bruto),
        **{k: v for k, v in result_to_dict(h).items() if k in ("langkah", "dasar_hukum", "asumsi", "peringatan")},
    }


@_tool
def calculate_pph21_permanent_monthly(**kw) -> dict:
    func = calc_monthly_ter_gross_up if kw.get("gross_up", False) else calc_monthly_ter
    h = func(
        _components(kw),
        parse_ptkp_status(kw["status_ptkp"]),
        _year(kw),
        kw["masa_pajak"],
        punya_npwp=kw.get("punya_npwp", True),
    )
    return _finish(h, kw)


@_tool
def calculate_pph21_permanent_annual(**kw) -> dict:
    components, note = _period_components(kw)
    h = calc_annual(
        components,
        parse_ptkp_status(kw["status_ptkp"]),
        _year(kw),
        punya_npwp=kw.get("punya_npwp", True),
        bulan_masa_perolehan=kw.get("bulan_masa_perolehan", 12),
        disetahunkan=kw.get("disetahunkan", False),
        neto_pemberi_kerja_sebelumnya=kw.get("neto_pemberi_kerja_sebelumnya", 0),
    )
    return _finish(_note(h, note), kw)


def _estimate_withheld_ter(kw: dict) -> tuple[Decimal, str]:
    if not kw.get("nilai_per_bulan") or kw.get("gross_up") or kw.get("pph_sudah_dipotong"):
        raise ValueError("pph_sudah_dipotong_ter_sama=true hanya dengan nilai_per_bulan=true, gross_up=false, "
                         "dan pph_sudah_dipotong=0")
    n = int(kw.get("bulan_masa_perolehan", 12)) - 1
    first_period = max(1, int(kw.get("masa_pajak", 12)) - n)
    monthly = calc_monthly_ter(_components(kw), parse_ptkp_status(kw["status_ptkp"]), _year(kw), first_period,
                                 punya_npwp=kw.get("punya_npwp", True)).pph_terutang
    return monthly * n, (f"PPh 21 yang sudah dipotong tidak diketahui; diperkirakan TER bulanan "
                         f"{format_rupiah(monthly)} x {n} masa = {format_rupiah(monthly * n)}, dengan anggapan "
                         "penghasilan sama setiap bulan. Ganti dengan jumlah di bukti potong bila ada.")


@_tool
def calculate_pph21_permanent_last_period(**kw) -> dict:
    components, note = _period_components(kw)
    func = calc_final_period_gross_up if kw.get("gross_up", False) else calc_final_period
    withheld, withheld_note = kw["pph_sudah_dipotong"], None
    if kw.get("pph_sudah_dipotong_ter_sama"):
        withheld, withheld_note = _estimate_withheld_ter(kw)
    h = func(
        components,
        parse_ptkp_status(kw["status_ptkp"]),
        _year(kw),
        withheld,
        punya_npwp=kw.get("punya_npwp", True),
        masa_pajak=kw.get("masa_pajak", 12),
        bulan_masa_perolehan=kw.get("bulan_masa_perolehan", 12),
        disetahunkan=kw.get("disetahunkan", False),
        neto_pemberi_kerja_sebelumnya=kw.get("neto_pemberi_kerja_sebelumnya", 0),
        pph_dipotong_pemberi_kerja_sebelumnya=kw.get("pph_dipotong_pemberi_kerja_sebelumnya", 0),
    )
    if withheld_note:
        h.asumsi.insert(0, withheld_note)
    return _finish(_note(h, note), kw)


@_tool
def calculate_pph21_pensioner_monthly(**kw) -> dict:
    h = calc_pensioner_monthly_ter(
        kw["uang_pensiun"],
        parse_ptkp_status(kw["status_ptkp"]),
        _year(kw),
        kw["masa_pajak"],
        penghasilan_lain=kw.get("penghasilan_lain", 0),
        punya_npwp=kw.get("punya_npwp", True),
    )
    return _finish(h, kw)


def _pensioner_annual_args(kw: dict) -> tuple[dict, str | None]:
    n, note = _month_factor(kw)
    return {
        "uang_pensiun_setahun": money(kw["uang_pensiun"]) * n,
        "penghasilan_lain_setahun": money(kw.get("penghasilan_lain", 0)) * n,
        "zakat_setahun": money(kw.get("zakat_via_pembayar_pensiun", 0)) * n,
        "punya_npwp": kw.get("punya_npwp", True),
        "bulan_masa_perolehan": kw.get("bulan_masa_perolehan", 12),
        "disetahunkan": kw.get("disetahunkan", False),
        "neto_pemberi_sebelumnya": kw.get("neto_pemberi_sebelumnya", 0),
    }, note


@_tool
def calculate_pph21_pensioner_annual(**kw) -> dict:
    args, note = _pensioner_annual_args(kw)
    h = calc_pensioner_annual(status=parse_ptkp_status(kw["status_ptkp"]), tahun=_year(kw), **args)
    return _finish(_note(h, note), kw)


@_tool
def calculate_pph21_pensioner_last_period(**kw) -> dict:
    args, note = _pensioner_annual_args(kw)
    h = _note(calc_pensioner_final_period(
        status=parse_ptkp_status(kw["status_ptkp"]),
        tahun=_year(kw),
        pph_sudah_dipotong=kw["pph_sudah_dipotong"],
        masa_pajak=kw.get("masa_pajak", 12),
        pph_dipotong_pemberi_sebelumnya=kw.get("pph_dipotong_pemberi_sebelumnya", 0),
        **args,
    ), note)
    return _finish(h, kw)


@_tool
def calculate_pph21_non_permanent(**kw) -> dict:
    scheme = _choice(WageScheme, kw["skema"], "skema")
    status_text = (kw.get("status_ptkp") or "").strip()
    h = calc_non_permanent_employee(
        kw["upah_per_periode"],
        scheme,
        _year(kw),
        jumlah_hari=kw.get("jumlah_hari", 1),
        status=parse_ptkp_status(status_text) if status_text else None,
        punya_npwp=kw.get("punya_npwp", True),
    )
    return _finish(h, kw)


@_tool
def calculate_pph21_non_employee(**kw) -> dict:
    h = calc_non_employee(
        kw["penghasilan_bruto"],
        _year(kw),
        punya_npwp=kw.get("punya_npwp", True),
        pembayaran_dikecualikan=kw.get("pembayaran_dikecualikan", 0),
        jasa_katering=kw.get("jasa_katering", False),
    )
    return _finish(h, kw, jenis_jasa=kw.get("jenis_jasa", ""))


@_tool
def calculate_pph21_commissioner(**kw) -> dict:
    h = calc_commissioner(
        kw["penghasilan_bruto"],
        parse_ptkp_status(kw["status_ptkp"]),
        _year(kw),
        punya_npwp=kw.get("punya_npwp", True),
    )
    return _finish(h, kw)


@_tool
def calculate_pph21_final(**kw) -> dict:
    kind = _choice(FinalIncomeType, kw["jenis"], "jenis")
    grade = (kw.get("golongan") or "").strip() or None
    payment_year = int(kw.get("tahun_pembayaran_ke", 1) or 1)
    if payment_year < 1:
        raise ValueError("tahun_pembayaran_ke minimal 1")
    if payment_year >= 3:
        h = calc_lump_sum_third_year(kind, kw["jumlah_bruto"], _year(kw),
                                          punya_npwp=kw.get("punya_npwp", True),
                                          dibayar_sebelumnya_tahun_ini=kw.get("dibayar_sebelumnya_tahun_ini", 0))
    else:
        h = calc_final(kind, kw["jumlah_bruto"], _year(kw), golongan=grade)
    return _finish(h, kw, golongan=grade or "")


@_tool
def calculate_pph21_direct_pasal_17(**kw) -> dict:
    kind = _choice(Article17DirectType, kw["jenis"], "jenis")
    h = calc_article17_direct(
        kind,
        kw["penghasilan_bruto"],
        _year(kw),
        punya_npwp=kw.get("punya_npwp", True),
    )
    return _finish(h, kw, jenis_kegiatan=kw.get("jenis_kegiatan", ""))


@_tool
def calculate_pph_pasal_26(**kw) -> dict:
    treaty_rate = kw.get("tarif_p3b_persen", -1)
    h = calc_pph26(
        kw["penghasilan_bruto"],
        _year(kw),
        negara_domisili=kw.get("negara_domisili", ""),
        tarif_p3b_persen=None if treaty_rate is None or treaty_rate < 0 else treaty_rate,
        ada_surat_keterangan_domisili=kw.get("ada_surat_keterangan_domisili", False),
    )
    return _finish(h, kw)


TOOL_SPECS = [
    (
        lookup_ptkp,
        S.PtkpArgs,
        "Tentukan kode status PTKP (TK/0 sampai K/3), nominal PTKP setahun, dan kategori TER "
        "dari status kawin serta jumlah tanggungan. Panggil ini lebih dulu bila pengguna hanya "
        "menyebut 'menikah, anak 1' dan belum menyebut kode PTKP.",
    ),
    (
        lookup_ter,
        S.TerArgs,
        "Cari tarif efektif rata-rata bulanan untuk suatu status PTKP dan penghasilan bruto sebulan. "
        "Gunakan untuk menjawab pertanyaan tentang tarif saja, tanpa menghitung PPh.",
    ),
    (
        lookup_pasal_17_rates,
        S.TahunArgs,
        "Ambil lapisan tarif progresif Pasal 17 untuk suatu tahun pajak.",
    ),
    (
        calculate_taxable_natura,
        S.NaturaArgs,
        "Tentukan berapa nilai natura dan/atau kenikmatan (makanan, kupon, bingkisan, laptop, "
        "olahraga, tempat tinggal, kendaraan, dst.) yang KENA pajak menurut PMK 66/2023, untuk satu "
        "masa pajak. Panggil ini dulu bila pengguna menyebut natura/fasilitas, lalu isi hasil "
        "natura_kena_pajak ke field natura_kena_pajak pada tool hitung PPh 21.",
    ),
    (
        find_legal_basis,
        S.DasarHukumArgs,
        "Ambil rujukan pasal dan ringkasan ketentuan untuk suatu topik. Ini SATU-SATUNYA sumber "
        "rujukan hukum yang boleh dikutip. Jangan pernah menyebut nomor pasal atau peraturan yang "
        "tidak dikembalikan tool ini atau field dasar_hukum pada hasil perhitungan.",
    ),
    (
        calculate_pph21_permanent_monthly,
        S.BulananArgs,
        "Hitung PPh 21 pegawai tetap untuk satu masa pajak Januari sampai November dengan metode "
        "tarif efektif rata-rata (TER). Nilai komponen adalah jumlah SEBULAN. Bila PPh 21 "
        "ditanggung penuh perusahaan (gross-up), isi gross_up=true dan jangan isi tunjangan_pph.",
    ),
    (
        calculate_pph21_permanent_annual,
        S.TahunanArgs,
        "Hitung PPh 21 pegawai tetap untuk satu tahun penuh dengan tarif Pasal 17, termasuk biaya "
        "jabatan dan PTKP. Nilai komponen adalah jumlah SETAHUN. Gunakan untuk bukti potong 1721-A1 "
        "atau bila pengguna bertanya total pajak setahun.",
    ),
    (
        calculate_pph21_permanent_last_period,
        S.MasaTerakhirArgs,
        "Hitung PPh 21 masa pajak terakhir (umumnya Desember, atau bulan pegawai berhenti bekerja): "
        "PPh setahun dihitung ulang dengan tarif Pasal 17 lalu dikurangi PPh yang sudah dipotong "
        "masa-masa sebelumnya. Nilai komponen adalah jumlah SETAHUN.",
    ),
    (
        calculate_pph21_pensioner_monthly,
        S.PensiunanBulananArgs,
        "Hitung PPh 21 pensiunan (penerima uang pensiun BERKALA/bulanan dari dana pensiun atau "
        "pembayar pensiun) untuk satu masa pajak selain masa pajak terakhir, metode TER. Nilai "
        "adalah jumlah SEBULAN. BUKAN untuk uang pensiun/manfaat pensiun/JHT yang dibayar "
        "SEKALIGUS, itu calculate_pph21_final atau calculate_pph21_direct_pasal_17.",
    ),
    (
        calculate_pph21_pensioner_annual,
        S.PensiunanTahunanArgs,
        "Hitung PPh 21 pensiunan setahun dengan tarif Pasal 17. Pengurang HANYA biaya pensiun "
        "(5%, maksimal Rp200.000/bulan atau Rp2.400.000/tahun) dan zakat melalui pembayar "
        "pensiun, BUKAN biaya jabatan. Nilai uang pensiun adalah jumlah SETAHUN.",
    ),
    (
        calculate_pph21_pensioner_last_period,
        S.PensiunanMasaTerakhirArgs,
        "Hitung PPh 21 pensiunan masa pajak terakhir (Desember, atau bulan uang pensiun berhenti): "
        "PPh setahun dihitung ulang dengan tarif Pasal 17 dan biaya pensiun sebagai pengurang, lalu "
        "dikurangi PPh yang sudah dipotong. BEDA dari calculate_pph21_permanent_last_period (pegawai "
        "tetap, memakai biaya jabatan).",
    ),
    (
        calculate_pph21_non_permanent,
        S.TidakTetapArgs,
        "Hitung PPh 21 pegawai tidak tetap dengan upah harian, mingguan, satuan, borongan, atau bulanan. "
        "Untuk pekerja di IKN pada pemberi kerja yang memanfaatkan fasilitas, isi fasilitas_ikn=true.",
    ),
    (
        calculate_pph21_non_employee,
        S.BukanPegawaiArgs,
        "Hitung PPh 21 bukan pegawai seperti tenaga ahli, konsultan, pengacara, dokter praktik, "
        "atau pemberi jasa lain. Dasar pengenaan pajak 50% dari bruto masa pajak ini, tarif "
        "Pasal 17 diterapkan per masa pajak (bukan kumulatif lintas masa pajak). BUKAN untuk "
        "anggota dewan komisaris/pengawas, itu tool terpisah (calculate_pph21_commissioner) "
        "karena dasar pengenaan dan tarifnya berbeda.",
    ),
    (
        calculate_pph21_commissioner,
        S.DewanKomisarisArgs,
        "Hitung PPh 21 untuk anggota dewan komisaris atau dewan pengawas yang menerima "
        "penghasilan tidak teratur dari perusahaan tempat ia BUKAN Pegawai Tetap (mis. honorarium "
        "komisaris). Dasar pengenaan pajak adalah 100% bruto (TIDAK dikurangi 50% seperti bukan "
        "pegawai), tarif efektif bulanan (TER) berdasarkan status PTKP, sama seperti pegawai "
        "tetap bulanan.",
    ),
    (
        calculate_pph21_final,
        S.FinalArgs,
        "Hitung PPh 21 yang bersifat final: uang pesangon, uang manfaat pensiun atau JHT yang "
        "dibayar sekaligus, dan honorarium PNS yang dibebankan pada APBN/APBD. Juga bagian pesangon atau "
        "manfaat pensiun/THT/JHT yang dibayar pada tahun kalender KETIGA dan seterusnya (isi "
        "tahun_pembayaran_ke=3 atau lebih; tidak final, tarif Pasal 17).",
    ),
    (
        calculate_pph21_direct_pasal_17,
        S.Pasal17LangsungArgs,
        "Hitung PPh 21 untuk tiga kategori: (1) peserta_kegiatan, hadiah/penghargaan dari lomba "
        "atau kegiatan; (2) peserta_pensiun_pegawai, penarikan uang manfaat pensiun oleh pegawai "
        "aktif; (3) mantan_pegawai, jasa produksi/tantiem/gratifikasi/bonus yang diterima setelah "
        "berhenti bekerja. Ketiganya dikenakan tarif Pasal 17 progresif LANGSUNG atas 100% "
        "penghasilan bruto, TIDAK dikurangi PTKP, TIDAK kumulatif antar masa pajak.",
    ),
    (
        calculate_pph_pasal_26,
        S.Pph26Args,
        "Hitung PPh Pasal 26 atas penghasilan yang dibayarkan kepada Wajib Pajak luar negeri "
        "(bukan subjek pajak dalam negeri). Tarif 20% atau tarif P3B bila ada Surat Keterangan Domisili.",
    ),
]
