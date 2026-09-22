from __future__ import annotations

from decimal import Decimal

from .models import IncomeComponents, PPh21Result, PTKPStatus, Step
from .ptkp import ptkp_breakdown
from .rates import RateTable, calc_progressive, load_rates
from .rounding import format_rupiah, money, round_down, round_rupiah

ZERO = Decimal(0)


def apply_non_npwp(result: PPh21Result, pph: Decimal, table: RateTable, punya_npwp: bool) -> None:
    result.pph_sebelum_penalti = round_rupiah(pph)
    if punya_npwp:
        result.penalti_non_npwp = ZERO
        result.pph_terutang = result.pph_sebelum_penalti
        return

    total = round_rupiah(pph * table.faktor_non_npwp)
    result.penalti_non_npwp = total - result.pph_sebelum_penalti
    result.pph_terutang = total
    result.add_step(
        "Tarif lebih tinggi karena tidak ber-NPWP",
        total,
        formula=f"{result.pph_sebelum_penalti} x {table.faktor_non_npwp}",
        catatan="Penerima penghasilan tanpa NPWP dikenakan tarif 20% lebih tinggi.",
    )
    result.dasar_hukum.append("UU PPh Pasal 21 ayat (5a)")


def calc_monthly_ter(
    komponen: IncomeComponents,
    status: PTKPStatus,
    tahun: int,
    masa_pajak: int,
    punya_npwp: bool = True,
) -> PPh21Result:
    if not 1 <= masa_pajak <= 12:
        raise ValueError("masa_pajak harus 1 sampai 12")

    table = load_rates(tahun)
    gross = komponen.bruto()
    category = table.ter_category(status)
    bracket = table.monthly_ter_rate(category, gross)

    result = PPh21Result(
        jenis_perhitungan="pegawai_tetap_bulanan_ter",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
        metode_tarif=f"TER kategori {category.value}, tarif {bracket.persen}%",
    )
    result.peringatan.extend(table.verification_warning())

    result.add_step("Penghasilan bruto sebulan", gross, formula=_gross_breakdown(komponen))
    result.add_step(
        f"Status PTKP {status.value} masuk kategori TER {category.value}",
        catatan="Kategori TER ditentukan status PTKP, bukan besaran penghasilan.",
    )
    upper = "tak terbatas" if bracket.batas_atas is None else format_rupiah(bracket.batas_atas)
    result.add_step(
        f"Tarif efektif bulanan {bracket.persen}%",
        catatan=f"Bracket penghasilan bruto sampai dengan {upper}.",
    )

    pph = gross * bracket.persen / Decimal(100)
    result.add_step(
        "PPh 21 masa (sebelum penyesuaian)",
        pph,
        formula=f"{gross} x {bracket.persen}%",
    )
    apply_non_npwp(result, pph, table, punya_npwp)

    result.dasar_hukum.extend(["PP No. 58 Tahun 2023", "PMK No. 168 Tahun 2023"])
    result.asumsi.append(
        "Metode TER dipakai untuk masa pajak selain masa pajak terakhir. "
        "Pengurang seperti biaya jabatan dan iuran pensiun tidak diperhitungkan "
        "di sini, melainkan pada perhitungan ulang masa pajak terakhir."
    )

    if masa_pajak == 12:
        result.peringatan.append(
            "Masa pajak 12 (Desember) umumnya merupakan masa pajak terakhir dan "
            "harus dihitung ulang dengan tarif Pasal 17, bukan dengan TER. "
            "Gunakan perhitungan masa pajak terakhir."
        )

    if komponen.deductions_excluding_job_expense() > 0:
        result.asumsi.append(
            "Iuran yang dibayar sendiri oleh pegawai tercatat namun tidak "
            "mengurangi dasar pengenaan pada metode TER."
        )
    if komponen.iuran_bpjs_kesehatan_dibayar_pegawai > 0:
        result.asumsi.append(
            "Iuran BPJS Kesehatan yang dibayar pegawai bukan merupakan pengurang."
        )

    return result


def calc_monthly_ter_gross_up(
    komponen: IncomeComponents,
    status: PTKPStatus,
    tahun: int,
    masa_pajak: int,
    punya_npwp: bool = True,
) -> PPh21Result:
    if komponen.tunjangan_pph:
        raise ValueError(
            "gross-up menghitung tunjangan PPh sendiri; kosongkan tunjangan_pph (isi 0)"
        )
    table = load_rates(tahun)
    other_gross = komponen.bruto()
    factor = Decimal(1) if punya_npwp else table.faktor_non_npwp
    category = table.ter_category(status)

    allowance = ZERO
    for bracket in table.monthly_ter_brackets(category):
        r = bracket.persen / Decimal(100) * factor
        if r >= 1:  # pragma: no cover
            raise ValueError("tarif efektif >= 100%, gross-up tidak terdefinisi")
        candidate = round_rupiah(other_gross * r / (1 - r))
        if bracket.batas_atas is None or other_gross + candidate <= bracket.batas_atas:
            allowance = candidate
            break

    for _ in range(5):
        result = calc_monthly_ter(
            komponen.model_copy(update={"tunjangan_pph": allowance}),
            status, tahun, masa_pajak, punya_npwp=punya_npwp,
        )
        if result.pph_terutang == allowance:
            break
        allowance = result.pph_terutang
    else:  # pragma: no cover
        raise ValueError("gross-up tidak konvergen; periksa tabel TER")

    result.jenis_perhitungan = "pegawai_tetap_bulanan_ter_gross_up"
    result.langkah.insert(
        0,
        Step(
            label="Tunjangan PPh (gross-up penuh)",
            nilai=allowance,
            formula=f"{other_gross} x r / (1 - r), r = tarif TER bracket bruto hasil gross-up",
            catatan="PPh 21 ditanggung pemberi kerja dan menjadi penghasilan pegawai.",
        ),
    )
    result.asumsi.append(
        "PPh 21 ditanggung penuh pemberi kerja (full gross-up): tunjangan PPh sama "
        "dengan PPh 21 terutang atas penghasilan bruto termasuk tunjangan itu sendiri."
    )
    result.dasar_hukum.append("PMK No. 168 Tahun 2023 Lampiran I.4 (contoh gross-up)")
    return result


def calc_annual(
    komponen_setahun: IncomeComponents,
    status: PTKPStatus,
    tahun: int,
    punya_npwp: bool = True,
    bulan_masa_perolehan: int = 12,
    disetahunkan: bool = False,
    neto_pemberi_kerja_sebelumnya: Decimal | int | float = 0,
) -> PPh21Result:
    if not 1 <= bulan_masa_perolehan <= 12:
        raise ValueError("bulan_masa_perolehan harus 1 sampai 12")

    table = load_rates(tahun)
    gross = komponen_setahun.bruto()
    previous_net = money(neto_pemberi_kerja_sebelumnya)
    if previous_net < 0:
        raise ValueError("neto_pemberi_kerja_sebelumnya tidak boleh negatif")
    if gross == 0 and previous_net > 0:
        raise ValueError(
            "penghasilan dari pemberi kerja ini nol padahal neto_pemberi_kerja_sebelumnya diisi. "
            "Field itu HANYA untuk neto dari bukti potong pemberi kerja LAMA; masukkan gaji dan "
            "penghasilan dari pemberi kerja yang sedang menghitung ke gaji_pokok dan komponen lain"
        )

    result = PPh21Result(
        jenis_perhitungan="pegawai_tetap_tahunan",
        tahun_pajak=tahun,
        penghasilan_bruto=gross,
        metode_tarif="Tarif Pasal 17 UU HPP",
    )
    result.peringatan.extend(table.verification_warning())
    result.add_step(
        "Penghasilan bruto (pemberi kerja ini)",
        gross,
        formula=_gross_breakdown(komponen_setahun),
    )

    job_rate = money(table.biaya_jabatan["persen"])
    job_computed = gross * job_rate / Decimal(100)
    job_cap = min(
        money(table.biaya_jabatan["maksimal_sebulan"]) * bulan_masa_perolehan,
        money(table.biaya_jabatan["maksimal_setahun"]),
    )
    job_expense = min(job_computed, job_cap)
    result.add_step(
        "Biaya jabatan",
        job_expense,
        formula=f"min({job_rate}% x {gross} = {job_computed}, batas {job_cap})",
        catatan="Paling banyak Rp500.000 sebulan atau Rp6.000.000 setahun.",
    )

    other_deductions = komponen_setahun.deductions_excluding_job_expense()
    if other_deductions > 0:
        result.add_step(
            "Iuran pensiun/JHT/JP yang dibayar pegawai dan zakat",
            other_deductions,
            formula=_deduction_breakdown(komponen_setahun),
        )

    net = gross - job_expense - other_deductions
    if previous_net > 0:
        this_net = net
        result.add_step(
            "Penghasilan neto (pemberi kerja ini)",
            this_net,
            formula=f"{gross} - {job_expense} - {other_deductions}",
        )
        result.add_step(
            "Penghasilan neto pemberi kerja sebelumnya",
            previous_net,
            catatan="Dari bukti pemotongan masa pajak terakhir pemberi kerja sebelumnya.",
        )
        net = this_net + previous_net
        result.add_step("Penghasilan neto setahun", net, formula=f"{this_net} + {previous_net}")
        result.asumsi.append(
            "Pegawai pindah kerja di tahun pajak yang sama dan menyerahkan bukti "
            "pemotongan pemberi kerja sebelumnya, sehingga penghasilan neto kedua "
            "pemberi kerja digabung sebelum PTKP dan tarif Pasal 17 diterapkan."
        )
    else:
        result.add_step("Penghasilan neto setahun", net, formula=f"{gross} - {job_expense} - {other_deductions}")

    base_net = net
    if disetahunkan and bulan_masa_perolehan < 12:
        base_net = net * Decimal(12) / Decimal(bulan_masa_perolehan)
        result.add_step(
            "Penghasilan neto disetahunkan",
            base_net,
            formula=f"{net} x 12 / {bulan_masa_perolehan}",
        )

    ptkp = table.annual_ptkp(status)
    result.add_step(
        f"PTKP {status.value}",
        ptkp,
        formula=" + ".join(ptkp_breakdown(status, table)),
    )

    raw_pkp = max(base_net - ptkp, ZERO)
    pkp = round_down(raw_pkp, table.pembulatan_pkp)
    result.add_step(
        "Penghasilan Kena Pajak",
        pkp,
        formula=f"max({base_net} - {ptkp}, 0) dibulatkan ke bawah kelipatan {table.pembulatan_pkp}",
    )
    result.dasar_pengenaan_pajak = pkp

    pph, breakdown = calc_progressive(pkp, table.tarif_pasal_17)
    for bracket, taxed, tax in breakdown:
        result.add_step(
            f"Lapisan {bracket.persen}%",
            tax,
            formula=f"{taxed} x {bracket.persen}%",
        )
    result.add_step("PPh 21 setahun (sebelum penyesuaian)", pph)

    if disetahunkan and bulan_masa_perolehan < 12:
        pph = pph * Decimal(bulan_masa_perolehan) / Decimal(12)
        result.add_step(
            "PPh 21 sesuai masa perolehan",
            pph,
            formula=f"PPh disetahunkan x {bulan_masa_perolehan} / 12",
        )

    apply_non_npwp(result, pph, table, punya_npwp)

    result.dasar_hukum.extend(
        [
            "UU PPh Pasal 17 ayat (1) huruf a s.t.d.t.d UU HPP",
            "UU PPh Pasal 7 ayat (1)",
            "PMK No. 168 Tahun 2023",
        ]
    )
    if previous_net > 0:
        result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 10 ayat (3)")
    if bulan_masa_perolehan < 12:
        result.asumsi.append(
            f"Masa perolehan penghasilan {bulan_masa_perolehan} bulan"
            + (" dan penghasilan neto disetahunkan." if disetahunkan else " tanpa disetahunkan.")
        )
    return result


def calc_final_period(
    komponen_setahun: IncomeComponents,
    status: PTKPStatus,
    tahun: int,
    pph_sudah_dipotong: Decimal | int | float,
    punya_npwp: bool = True,
    masa_pajak: int = 12,
    bulan_masa_perolehan: int = 12,
    disetahunkan: bool = False,
    neto_pemberi_kerja_sebelumnya: Decimal | int | float = 0,
    pph_dipotong_pemberi_kerja_sebelumnya: Decimal | int | float = 0,
) -> PPh21Result:
    annual = calc_annual(
        komponen_setahun,
        status,
        tahun,
        punya_npwp=punya_npwp,
        bulan_masa_perolehan=bulan_masa_perolehan,
        disetahunkan=disetahunkan,
        neto_pemberi_kerja_sebelumnya=neto_pemberi_kerja_sebelumnya,
    )

    withheld_here = money(pph_sudah_dipotong)
    withheld_previous = money(pph_dipotong_pemberi_kerja_sebelumnya)
    withheld = withheld_here + withheld_previous
    difference = annual.pph_terutang - withheld

    result = PPh21Result(
        jenis_perhitungan="pegawai_tetap_masa_pajak_terakhir",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=annual.penghasilan_bruto,
        dasar_pengenaan_pajak=annual.dasar_pengenaan_pajak,
        metode_tarif=annual.metode_tarif,
        langkah=list(annual.langkah),
        dasar_hukum=list(annual.dasar_hukum),
        asumsi=list(annual.asumsi),
        peringatan=list(annual.peringatan),
    )
    result.add_step("PPh 21 terutang setahun", annual.pph_terutang)
    result.add_step(
        "PPh 21 yang telah dipotong pemberi kerja ini",
        withheld_here,
        catatan="Jumlah dari bukti potong masa-masa pajak sebelumnya di pemberi kerja ini.",
    )
    if withheld_previous > 0:
        result.add_step(
            "PPh 21 yang telah dipotong pemberi kerja sebelumnya",
            withheld_previous,
            catatan="Dari Form 1721-A1 pemberi kerja sebelumnya.",
        )
    result.add_step(
        "PPh 21 masa pajak terakhir",
        difference,
        formula=f"{annual.pph_terutang} - {withheld}",
    )

    result.pph_sebelum_penalti = annual.pph_sebelum_penalti
    result.penalti_non_npwp = annual.penalti_non_npwp
    result.pph_terutang = round_rupiah(difference) if difference >= 0 else -round_rupiah(-difference)

    if difference < 0:
        result.peringatan.append(
            f"Terjadi kelebihan potong sebesar {-difference}. Kelebihan ini "
            f"dikembalikan kepada pegawai pada masa pajak terakhir."
        )
    result.dasar_hukum.append("PMK No. 168 Tahun 2023 Pasal 15 ayat (1) huruf b dan ayat (2)")
    return result


def calc_final_period_gross_up(
    komponen_setahun: IncomeComponents,
    status: PTKPStatus,
    tahun: int,
    pph_sudah_dipotong: Decimal | int | float,
    **options,
) -> PPh21Result:
    if komponen_setahun.tunjangan_pph:
        raise ValueError(
            "gross-up menghitung tunjangan PPh sendiri; kosongkan tunjangan_pph (isi 0)"
        )
    withheld = money(pph_sudah_dipotong)

    def compute(t: Decimal) -> PPh21Result:
        return calc_final_period(
            komponen_setahun.model_copy(update={"tunjangan_pph": withheld + t}),
            status, tahun, withheld, **options,
        )

    allowance = ZERO
    seen: set[Decimal] = set()
    for _ in range(60):
        result = compute(allowance)
        if result.pph_terutang == allowance:
            break
        if result.pph_terutang in seen:
            allowance = max(allowance, result.pph_terutang)
            result = compute(allowance)
            break
        seen.add(allowance)
        allowance = result.pph_terutang
    else:  # pragma: no cover
        raise ValueError("gross-up masa pajak terakhir tidak konvergen")

    result.jenis_perhitungan = "pegawai_tetap_masa_pajak_terakhir_gross_up"
    result.langkah.insert(
        0,
        Step(
            label="Tunjangan PPh setahun (gross-up penuh)",
            nilai=withheld + allowance,
            formula=f"tunjangan Januari-November {withheld} + tunjangan masa terakhir {allowance}",
            catatan="Dicari supaya total tunjangan PPh setahun sama dengan PPh 21 setahun.",
        ),
    )
    result.asumsi.append(
        "PPh 21 ditanggung penuh pemberi kerja sepanjang tahun (full gross-up): tunjangan "
        "PPh masa-masa sebelumnya sama dengan PPh yang sudah dipotong, dan tunjangan masa "
        "terakhir dihitung supaya total tunjangan sama dengan PPh 21 setahun."
    )
    result.peringatan.append(
        "Gross-up masa pajak terakhir tidak punya contoh resmi di Lampiran PMK 168/2023 "
        "(contoh resmi hanya gross-up masa TER, I.4); mekanismenya diturunkan dari definisi "
        "tunjangan PPh ditanggung pemberi kerja."
    )
    return result


def _gross_breakdown(k: IncomeComponents) -> str:
    parts = []
    labels = {
        "gaji_pokok": "gaji pokok",
        "tunjangan_tetap": "tunjangan tetap",
        "tunjangan_tidak_tetap": "tunjangan tidak tetap",
        "lembur": "lembur",
        "bonus_thr_komisi": "bonus/THR/komisi",
        "tunjangan_pph": "tunjangan PPh",
        "premi_jkk_dibayar_pemberi_kerja": "premi JKK (pemberi kerja)",
        "premi_jkm_dibayar_pemberi_kerja": "premi JKM (pemberi kerja)",
        "premi_bpjs_kesehatan_dibayar_pemberi_kerja": "premi BPJS Kesehatan (pemberi kerja)",
        "natura_kena_pajak": "natura kena pajak",
        "penghasilan_lain": "penghasilan lain",
    }
    for field, label in labels.items():
        value = getattr(k, field)
        if value:
            parts.append(f"{label} {value}")
    return " + ".join(parts) if parts else "0"


def _deduction_breakdown(k: IncomeComponents) -> str:
    parts = []
    labels = {
        "iuran_pensiun_dibayar_pegawai": "iuran pensiun",
        "iuran_jht_dibayar_pegawai": "iuran JHT",
        "iuran_jp_dibayar_pegawai": "iuran JP",
        "zakat_via_pemberi_kerja": "zakat via pemberi kerja",
    }
    for field, label in labels.items():
        value = getattr(k, field)
        if value:
            parts.append(f"{label} {value}")
    return " + ".join(parts) if parts else "0"
