from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result
from .rates import load_rates
from .rounding import format_rupiah, money

ZERO = Decimal(0)


def _cumulative_excess(current: Decimal, earlier: Decimal, limit: Decimal) -> Decimal:
    return max(earlier + current - limit, ZERO) - max(earlier - limit, ZERO)


def calc_in_kind(
    tahun: int,
    masa_pajak: int | None = None,
    makanan_di_tempat_kerja=0,
    kupon_makanan=0,
    nilai_makanan_kantor_sebulan=0,
    bingkisan_hari_raya=0,
    bingkisan_lain=0,
    bingkisan_lain_sebelumnya_tahun_ini=0,
    peralatan_kerja=0,
    kesehatan_akibat_kerja=0,
    fasilitas_olahraga=0,
    olahraga_sebelumnya_tahun_ini=0,
    tempat_tinggal_komunal=0,
    tempat_tinggal_individual=0,
    kendaraan=0,
    pegawai_punya_penyertaan_modal: bool = False,
    rata_rata_bruto_12_bulan=0,
    iuran_dana_pensiun_ditanggung=0,
    fasilitas_peribadatan=0,
    wajib_untuk_pekerjaan=0,
    natura_lain=0,
) -> PPh21Result:
    params = dict(locals())
    v = {
        k: money(x) for k, x in params.items()
        if k not in ("tahun", "masa_pajak", "pegawai_punya_penyertaan_modal")
    }
    for k, x in v.items():
        if x < 0:
            raise ValueError(f"{k} tidak boleh negatif")
    limits = load_rates(tahun).natura
    coupon_limit_monthly = limits["kupon_batas_sebulan"]
    gift_limit_yearly = limits["bingkisan_batas_setahun"]
    sports_limit_yearly = limits["olahraga_batas_setahun"]
    housing_limit_monthly = limits["tempat_tinggal_batas_sebulan"]
    vehicle_gross_limit = limits["kendaraan_batas_rata_bruto_sebulan"]

    result = PPh21Result(
        jenis_perhitungan="natura_kena_pajak",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=ZERO,
        metode_tarif="PMK 66/2023 (bukan perhitungan PPh; menghasilkan natura kena pajak)",
    )
    total = ZERO
    taxable = ZERO

    def record(label: str, value: Decimal, taxed: Decimal, formula: str, note: str) -> None:
        nonlocal total, taxable
        if value == 0:
            return
        total += value
        taxable += taxed
        result.add_step(f"{label}: kena pajak", taxed, formula=formula, catatan=note)

    record("Makanan/minuman di tempat kerja", v["makanan_di_tempat_kerja"], ZERO,
           "dikecualikan penuh", "Bagi seluruh pegawai (PMK 66/2023 Pasal 4 huruf a, Pasal 5 ayat (1) huruf a).")

    if v["kupon_makanan"]:
        limit = max(coupon_limit_monthly, v["nilai_makanan_kantor_sebulan"])
        taxed = max(v["kupon_makanan"] - limit, ZERO)
        record("Kupon makanan", v["kupon_makanan"], taxed,
               f"max({v['kupon_makanan']} - {limit}, 0)",
               f"Batas {format_rupiah(coupon_limit_monthly)} sebulan, atau nilai makanan di kantor bila lebih besar (Pasal 5 ayat (4)-(5)).")

    record("Bingkisan hari raya keagamaan", v["bingkisan_hari_raya"], ZERO,
           "dikecualikan penuh", "Bagi seluruh pegawai, tanpa batas nilai (Lampiran A angka 1).")

    if v["bingkisan_lain"]:
        taxed = _cumulative_excess(v["bingkisan_lain"], v["bingkisan_lain_sebelumnya_tahun_ini"], gift_limit_yearly)
        record("Bingkisan lain", v["bingkisan_lain"], taxed,
               f"kelebihan kumulatif di atas {gift_limit_yearly} (sebelumnya {v['bingkisan_lain_sebelumnya_tahun_ini']})",
               f"Batas {format_rupiah(gift_limit_yearly)} setahun, dihitung kumulatif (Lampiran A angka 2, contoh B.2).")

    record("Peralatan dan fasilitas kerja", v["peralatan_kerja"], ZERO,
           "dikecualikan penuh", "Komputer, laptop, telepon, pulsa, internet penunjang pekerjaan (Lampiran A angka 3).")
    record("Layanan kesehatan akibat kerja", v["kesehatan_akibat_kerja"], ZERO,
           "dikecualikan penuh", "Kecelakaan/penyakit akibat kerja, kedaruratan (Lampiran A angka 4).")

    if v["fasilitas_olahraga"]:
        taxed = _cumulative_excess(v["fasilitas_olahraga"], v["olahraga_sebelumnya_tahun_ini"], sports_limit_yearly)
        record("Fasilitas olahraga", v["fasilitas_olahraga"], taxed,
               f"kelebihan kumulatif di atas {sports_limit_yearly} (sebelumnya {v['olahraga_sebelumnya_tahun_ini']})",
               f"Batas {format_rupiah(sports_limit_yearly)} setahun; golf, pacuan kuda, balap perahu, terbang layang, otomotif tidak termasuk (Lampiran A angka 5).")

    record("Tempat tinggal komunal", v["tempat_tinggal_komunal"], ZERO,
           "dikecualikan penuh", "Mes, asrama, pondokan, barak (Lampiran A angka 6).")

    if v["tempat_tinggal_individual"]:
        taxed = max(v["tempat_tinggal_individual"] - housing_limit_monthly, ZERO)
        record("Tempat tinggal individual", v["tempat_tinggal_individual"], taxed,
               f"max({v['tempat_tinggal_individual']} - {housing_limit_monthly}, 0)",
               f"Batas {format_rupiah(housing_limit_monthly)} sebulan (Lampiran A angka 7).")

    if v["kendaraan"]:
        excluded = not pegawai_punya_penyertaan_modal and v["rata_rata_bruto_12_bulan"] <= vehicle_gross_limit
        record("Kendaraan", v["kendaraan"], ZERO if excluded else v["kendaraan"],
               "dikecualikan" if excluded else "kena pajak penuh",
               "Dikecualikan hanya bila pegawai tidak punya penyertaan modal dan rata-rata bruto 12 "
               f"bulan terakhir s.d. {format_rupiah(vehicle_gross_limit)} sebulan (Lampiran A angka 8).")

    record("Iuran dana pensiun ditanggung pemberi kerja", v["iuran_dana_pensiun_ditanggung"], ZERO,
           "dikecualikan penuh", "Dana pensiun yang disahkan OJK (Lampiran A angka 9).")
    record("Fasilitas peribadatan", v["fasilitas_peribadatan"], ZERO,
           "dikecualikan penuh", "Lampiran A angka 10.")
    record("Natura wajib untuk pekerjaan", v["wajib_untuk_pekerjaan"], ZERO,
           "dikecualikan penuh", "Seragam, alat keselamatan kerja, antar jemput, penginapan awak kapal, penanganan pandemi/bencana (Pasal 6).")
    record("Natura/kenikmatan lain", v["natura_lain"], v["natura_lain"],
           "kena pajak penuh", "Tidak termasuk jenis yang dikecualikan (Pasal 3).")

    result.penghasilan_bruto = total
    result.dasar_pengenaan_pajak = taxable
    result.pph_sebelum_penalti = ZERO
    result.pph_terutang = ZERO
    result.add_step("Total natura/kenikmatan", total)
    result.add_step("Natura kena pajak (isi ke natura_kena_pajak)", taxable)
    result.dasar_hukum.extend([
        "PMK No. 66 Tahun 2023 Pasal 3 sampai Pasal 7",
        "PMK No. 66 Tahun 2023 Lampiran huruf A dan B",
    ])
    result.asumsi.append(
        "Nilai natura adalah nilai untuk masa pajak ini. Untuk batasan setahun (bingkisan "
        "lain, olahraga), nilai yang sudah diterima sebelumnya di tahun yang sama wajib diisi "
        "supaya kelebihan kumulatif dihitung benar."
    )
    result.peringatan.append(
        "Natura di daerah tertentu (PMK 66/2023 Pasal 8) butuh penetapan DJP dan tidak dinilai "
        "di sini."
    )
    return result
