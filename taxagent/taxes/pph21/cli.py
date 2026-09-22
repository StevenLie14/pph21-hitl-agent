from __future__ import annotations

import argparse
import json
import re

from ...cli._common import DEFAULT_YEAR, error, rule, show_result
from ...tools import all_tool_names, call_tool
from .calc import available_years, format_rupiah, load_rates
from .calc.models import PTKPStatus
from .calc.rates import DATA_DIR, TaxYearNotAvailable

GROSS_COMPONENTS = [
    ("gaji-pokok", "gaji_pokok"),
    ("tunjangan-tetap", "tunjangan_tetap"),
    ("tunjangan-tidak-tetap", "tunjangan_tidak_tetap"),
    ("lembur", "lembur"),
    ("bonus", "bonus_thr_komisi"),
    ("tunjangan-pph", "tunjangan_pph"),
    ("premi-jkk", "premi_jkk_dibayar_perusahaan"),
    ("premi-jkm", "premi_jkm_dibayar_perusahaan"),
    ("premi-bpjs-kes", "premi_bpjs_kesehatan_dibayar_perusahaan"),
    ("natura", "natura_kena_pajak"),
    ("penghasilan-lain", "penghasilan_lain"),
    ("jht-perusahaan", "iuran_jht_dibayar_perusahaan"),
    ("jp-perusahaan", "iuran_jp_dibayar_perusahaan"),
    ("iuran-pensiun", "iuran_pensiun_dibayar_pegawai"),
    ("jht-pegawai", "iuran_jht_dibayar_pegawai"),
    ("jp-pegawai", "iuran_jp_dibayar_pegawai"),
    ("zakat", "zakat_via_pemberi_kerja"),
    ("bpjs-kes-pegawai", "iuran_bpjs_kesehatan_dibayar_pegawai"),
]


def cmd_rates(args) -> int:
    try:
        t = load_rates(args.tahun)
    except TaxYearNotAvailable as e:
        error(e)
        return 1
    rule(f"Tabel tarif {t.tahun_pajak}")
    print(f"Berlaku sejak : {t.berlaku_sejak}")
    print(f"Terverifikasi : {t.terverifikasi}")
    if not t.terverifikasi:
        print(f"                {t.catatan_verifikasi.strip()}")
    print("\nPTKP setahun:")
    for s in PTKPStatus:
        print(f"  {s.value:<6} {format_rupiah(t.annual_ptkp(s)):>16}   kategori TER {t.ter_category(s).value}")
    print("\nTarif Pasal 17:")
    lower = 0
    for bracket in t.tarif_pasal_17:
        upper = "ke atas" if bracket.batas_atas is None else f"s.d. {format_rupiah(bracket.batas_atas)}"
        print(f"  di atas {format_rupiah(lower):>18}  {upper:<22} {bracket.persen}%")
        lower = bracket.batas_atas if bracket.batas_atas is not None else lower
    print("\nJumlah bracket TER bulanan:")
    for cat in ("A", "B", "C"):
        print(f"  kategori {cat}: {len(t._ter_bulanan[cat])} bracket")
    print("\nDasar hukum:")
    for d in t.dasar_hukum:
        print(f"  - {d}")
    return 0


def cmd_verify(args) -> int:
    path = DATA_DIR / f"tarif_{args.tahun}.yaml"
    if not path.exists():
        error(f"Berkas {path.name} tidak ada. Tahun tersedia: {available_years()}")
        return 1
    if not args.konfirmasi:
        print(
            f"Perintah ini menandai tabel tarif {args.tahun} sebagai SUDAH diverifikasi,\n"
            "sehingga peringatan provenance berhenti muncul di setiap hasil hitung.\n"
            "Lakukan hanya setelah kamu mencocokkan seluruh tabel (terutama TER A/B/C)\n"
            "baris demi baris dengan lampiran peraturan resmi.\n\n"
            "Ulangi dengan --konfirmasi bila sudah."
        )
        return 1
    text = path.read_text(encoding="utf-8")
    new_text, n = re.subn(r"^(\s*terverifikasi:\s*)false\s*$", r"\1true", text, count=1, flags=re.M)
    if n == 0:
        error("Tidak menemukan baris 'terverifikasi: false'. Mungkin sudah true.")
        return 1
    path.write_text(new_text, encoding="utf-8")
    print(f"Tabel tarif {args.tahun} ditandai terverifikasi.")
    return 0


def cmd_ptkp(args) -> int:
    return show_result(call_tool("lookup_ptkp", kawin=args.kawin, jumlah_tanggungan=args.tanggungan,
                                 tahun_pajak=args.tahun))


def _permanent_employee_args(args, **extra) -> dict:
    kw = {dest: getattr(args, dest) for _, dest in GROSS_COMPONENTS}
    return kw | {"status_ptkp": args.status, "tahun_pajak": args.tahun, "punya_npwp": not args.tanpa_npwp} | extra


def cmd_monthly(args) -> int:
    kw = _permanent_employee_args(args, masa_pajak=args.masa, gross_up=args.gross_up)
    return show_result(call_tool("calculate_pph21_permanent_monthly", **kw))


def cmd_annual(args) -> int:
    kw = _permanent_employee_args(args, bulan_masa_perolehan=args.bulan, disetahunkan=args.disetahunkan,
                        neto_pemberi_kerja_sebelumnya=args.neto_pemberi_sebelumnya)
    return show_result(call_tool("calculate_pph21_permanent_annual", **kw))


def cmd_final_period(args) -> int:
    kw = _permanent_employee_args(
        args, bulan_masa_perolehan=args.bulan, disetahunkan=args.disetahunkan, pph_sudah_dipotong=args.sudah_dipotong,
        masa_pajak=args.masa, neto_pemberi_kerja_sebelumnya=args.neto_pemberi_sebelumnya,
        pph_dipotong_pemberi_kerja_sebelumnya=args.dipotong_pemberi_sebelumnya, gross_up=args.gross_up,
    )
    return show_result(call_tool("calculate_pph21_permanent_last_period", **kw))


def _pensioner_args(args, **extra) -> dict:
    return {"uang_pensiun": args.uang_pensiun, "penghasilan_lain": args.penghasilan_lain, "status_ptkp": args.status,
            "tahun_pajak": args.tahun, "punya_npwp": not args.tanpa_npwp} | extra


def _pensioner_annual_args(args, **extra) -> dict:
    return _pensioner_args(args, zakat_via_pembayar_pensiun=args.zakat, bulan_masa_perolehan=args.bulan,
                      disetahunkan=args.disetahunkan, neto_pemberi_sebelumnya=args.neto_pemberi_sebelumnya, **extra)


def cmd_pensioner_monthly(args) -> int:
    return show_result(call_tool("calculate_pph21_pensioner_monthly", **_pensioner_args(args, masa_pajak=args.masa)))


def cmd_pensioner_annual(args) -> int:
    return show_result(call_tool("calculate_pph21_pensioner_annual", **_pensioner_annual_args(args)))


def cmd_pensioner_final_period(args) -> int:
    kw = _pensioner_annual_args(args, pph_sudah_dipotong=args.sudah_dipotong, masa_pajak=args.masa,
                            pph_dipotong_pemberi_sebelumnya=args.dipotong_pemberi_sebelumnya)
    return show_result(call_tool("calculate_pph21_pensioner_last_period", **kw))


def cmd_non_permanent(args) -> int:
    return show_result(call_tool(
        "calculate_pph21_non_permanent", upah_per_periode=args.upah, skema=args.skema, jumlah_hari=args.hari,
        status_ptkp=args.status or "", punya_npwp=not args.tanpa_npwp, tahun_pajak=args.tahun,
    ))


def cmd_non_employee(args) -> int:
    return show_result(call_tool(
        "calculate_pph21_non_employee", penghasilan_bruto=args.bruto, pembayaran_dikecualikan=args.dikecualikan,
        jasa_katering=args.katering, punya_npwp=not args.tanpa_npwp, tahun_pajak=args.tahun,
    ))


def cmd_commissioner(args) -> int:
    return show_result(call_tool(
        "calculate_pph21_commissioner", penghasilan_bruto=args.bruto, status_ptkp=args.status,
        punya_npwp=not args.tanpa_npwp, tahun_pajak=args.tahun,
    ))


def cmd_final(args) -> int:
    return show_result(call_tool(
        "calculate_pph21_final", jenis=args.jenis, jumlah_bruto=args.bruto, golongan=args.golongan or "",
        tahun_pajak=args.tahun,
    ))


def cmd_article17_direct(args) -> int:
    return show_result(call_tool(
        "calculate_pph21_direct_pasal_17", jenis=args.jenis, penghasilan_bruto=args.bruto,
        punya_npwp=not args.tanpa_npwp, tahun_pajak=args.tahun,
    ))


def cmd_pph26(args) -> int:
    return show_result(call_tool(
        "calculate_pph_pasal_26", penghasilan_bruto=args.bruto, negara_domisili=args.negara or "",
        tarif_p3b_persen=args.tarif_p3b, ada_surat_keterangan_domisili=args.skd, tahun_pajak=args.tahun,
    ))


def cmd_tool(args) -> int:
    try:
        kw = json.loads(args.json) if args.json else {}
    except json.JSONDecodeError as e:
        error(f"JSON tidak valid: {e}")
        return 1
    try:
        return show_result(call_tool(args.nama, **kw))
    except KeyError as e:
        error(e)
        return 1


def _add_year_npwp(p: argparse.ArgumentParser, npwp: bool = True) -> None:
    p.add_argument("--year", dest="tahun", type=int, default=DEFAULT_YEAR)
    if npwp:
        p.add_argument("--tanpa-npwp", action="store_true")


def _add_permanent_employee(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("komponen penghasilan (rupiah penuh)")
    for flag, dest in GROSS_COMPONENTS:
        g.add_argument(f"--{flag}", dest=dest, type=float, default=0)
    p.add_argument("--status", required=True, help="Kode PTKP, misalnya K/1")
    _add_year_npwp(p)


def _add_previous_net(p: argparse.ArgumentParser, help_text: str) -> None:
    p.add_argument("--neto-pemberi-sebelumnya", dest="neto_pemberi_sebelumnya", type=float, default=0, help=help_text)


def _add_pensioner(p: argparse.ArgumentParser, annual: bool = False) -> None:
    p.add_argument("--uang-pensiun", dest="uang_pensiun", type=float, required=True)
    p.add_argument("--penghasilan-lain", dest="penghasilan_lain", type=float, default=0,
                   help="Mis. uang pensiun ketiga belas atau THR dari pembayar pensiun yang sama")
    p.add_argument("--status", required=True, help="Kode PTKP, misalnya K/1")
    _add_year_npwp(p)
    if annual:
        p.add_argument("--zakat", type=float, default=0, help="Zakat melalui pembayar pensiun, setahun")
        p.add_argument("--bulan", type=int, default=12, help="Bulan uang pensiun diterima dari pembayar ini")
        p.add_argument("--disetahunkan", action="store_true")
        _add_previous_net(p, "Penghasilan NETO dari pemberi kerja/pembayar sebelumnya di tahun yang sama")


def register(sub) -> None:
    t = sub.add_parser("rates", help="Tampilkan tabel tarif satu tahun pajak")
    _add_year_npwp(t, npwp=False)
    t.set_defaults(handler=cmd_rates)

    v = sub.add_parser("verify", help="Tandai tabel tarif sebagai sudah diverifikasi")
    v.add_argument("--year", dest="tahun", type=int, required=True)
    v.add_argument("--konfirmasi", action="store_true")
    v.set_defaults(handler=cmd_verify)

    pt = sub.add_parser("ptkp", help="Tentukan status dan nominal PTKP")
    pt.add_argument("--kawin", action="store_true")
    pt.add_argument("--tanggungan", type=int, default=0)
    _add_year_npwp(pt, npwp=False)
    pt.set_defaults(handler=cmd_ptkp)

    hs = sub.add_parser("calculate", help="Hitung PPh 21 secara deterministik (tanpa LLM)").add_subparsers(
        dest="calculation", required=True)
    previous_net_help = "Penghasilan NETO dari bukti pemotongan pemberi kerja sebelumnya (pindah kerja di tahun yang sama)"

    b = hs.add_parser("monthly", help="Pegawai tetap, masa pajak Januari s.d. November (TER)")
    _add_permanent_employee(b)
    b.add_argument("--masa", type=int, required=True)
    b.add_argument("--gross-up", dest="gross_up", action="store_true",
                   help="PPh 21 ditanggung penuh pemberi kerja; tunjangan PPh dihitung otomatis")
    b.set_defaults(handler=cmd_monthly)

    th = hs.add_parser("annual", help="Pegawai tetap, setahun penuh (Pasal 17)")
    _add_permanent_employee(th)
    th.add_argument("--bulan", type=int, default=12, help="Bulan masa perolehan penghasilan")
    th.add_argument("--disetahunkan", action="store_true")
    _add_previous_net(th, previous_net_help)
    th.set_defaults(handler=cmd_annual)

    d = hs.add_parser("final-period", help="Pegawai tetap, masa pajak terakhir")
    _add_permanent_employee(d)
    d.add_argument("--sudah-dipotong", dest="sudah_dipotong", type=float, required=True)
    d.add_argument("--masa", type=int, default=12)
    d.add_argument("--bulan", type=int, default=12)
    d.add_argument("--disetahunkan", action="store_true")
    _add_previous_net(d, previous_net_help)
    d.add_argument("--dipotong-pemberi-sebelumnya", dest="dipotong_pemberi_sebelumnya", type=float, default=0,
                   help="PPh 21 yang sudah dipotong pemberi kerja sebelumnya, dari bukti pemotongannya")
    d.add_argument("--gross-up", dest="gross_up", action="store_true",
                   help="PPh 21 ditanggung penuh pemberi kerja sepanjang tahun; tunjangan PPh Desember dihitung otomatis")
    d.set_defaults(handler=cmd_final_period)

    pb = hs.add_parser("pensioner-monthly", help="Pensiunan, masa pajak selain masa pajak terakhir (TER)")
    _add_pensioner(pb)
    pb.add_argument("--masa", type=int, required=True)
    pb.set_defaults(handler=cmd_pensioner_monthly)

    pth = hs.add_parser("pensioner-annual", help="Pensiunan, setahun (Pasal 17, biaya pensiun)")
    _add_pensioner(pth, annual=True)
    pth.set_defaults(handler=cmd_pensioner_annual)

    pd = hs.add_parser("pensioner-final-period", help="Pensiunan, masa pajak terakhir")
    _add_pensioner(pd, annual=True)
    pd.add_argument("--sudah-dipotong", dest="sudah_dipotong", type=float, required=True)
    pd.add_argument("--masa", type=int, default=12)
    pd.add_argument("--dipotong-pemberi-sebelumnya", dest="dipotong_pemberi_sebelumnya", type=float, default=0,
                    help="PPh 21 terutang di pemberi kerja/pembayar sebelumnya, dari bukti pemotongannya")
    pd.set_defaults(handler=cmd_pensioner_final_period)

    tt = hs.add_parser("non-permanent", help="Pegawai tidak tetap")
    tt.add_argument("--upah", type=float, required=True)
    tt.add_argument("--skema", default="harian", choices=["harian", "mingguan", "satuan", "borongan", "bulanan"])
    tt.add_argument("--hari", type=int, default=1)
    tt.add_argument("--status", default="")
    _add_year_npwp(tt)
    tt.set_defaults(handler=cmd_non_permanent)

    bp = hs.add_parser("non-employee", help="Tenaga ahli dan pemberi jasa")
    bp.add_argument("--bruto", type=float, required=True)
    bp.add_argument("--dikecualikan", type=float, default=0,
                    help="Upah tenaga kerja/material/pihak ketiga yang dibuktikan faktur (bukan untuk katering)")
    bp.add_argument("--katering", action="store_true", help="Jasa katering: tidak ada pengecualian bruto")
    _add_year_npwp(bp)
    bp.set_defaults(handler=cmd_non_employee)

    dk = hs.add_parser("commissioner",
                       help="Anggota dewan komisaris/pengawas berpenghasilan tidak teratur (BUKAN kategori 'non-employee')")
    dk.add_argument("--bruto", type=float, required=True)
    dk.add_argument("--status", required=True, help="Kode PTKP, mis. TK/0")
    _add_year_npwp(dk)
    dk.set_defaults(handler=cmd_commissioner)

    f = hs.add_parser("final", help="PPh 21 final")
    f.add_argument("--jenis", required=True, choices=["pesangon", "manfaat_pensiun", "honorarium_pns"])
    f.add_argument("--bruto", type=float, required=True)
    f.add_argument("--golongan", default="")
    _add_year_npwp(f, npwp=False)
    f.set_defaults(handler=cmd_final)

    p17 = hs.add_parser("article17-direct",
                        help="Peserta kegiatan, penarikan manfaat pensiun (masih pegawai), atau mantan pegawai")
    p17.add_argument("--jenis", required=True, choices=["peserta_kegiatan", "peserta_pensiun_pegawai", "mantan_pegawai"])
    p17.add_argument("--bruto", type=float, required=True)
    _add_year_npwp(p17)
    p17.set_defaults(handler=cmd_article17_direct)

    p26 = hs.add_parser("pph26", help="PPh Pasal 26 untuk WP luar negeri")
    p26.add_argument("--bruto", type=float, required=True)
    p26.add_argument("--negara", default="")
    p26.add_argument("--tarif-p3b", dest="tarif_p3b", type=float, default=-1)
    p26.add_argument("--skd", action="store_true", help="Ada Surat Keterangan Domisili")
    _add_year_npwp(p26, npwp=False)
    p26.set_defaults(handler=cmd_pph26)

    tl = sub.add_parser("tool", help="Panggil satu tool langsung dengan argumen JSON")
    tl.add_argument("nama", choices=all_tool_names())
    tl.add_argument("--json", default="{}")
    tl.set_defaults(handler=cmd_tool)
