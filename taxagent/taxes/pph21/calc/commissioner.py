from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result, PTKPStatus
from .rates import load_rates
from .rounding import money, round_rupiah

ZERO = Decimal(0)


def calc_commissioner(
    bruto,
    status: PTKPStatus,
    tahun: int,
    punya_npwp: bool = True,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    gross = money(bruto)
    if gross < 0:
        raise ValueError("penghasilan bruto tidak boleh negatif")

    result = PPh21Result(
        jenis_perhitungan="dewan_komisaris",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.extend(
        [
            "PP No. 58 Tahun 2023",
            "PMK No. 168 Tahun 2023 Pasal 12 ayat (1) dan Pasal 16 ayat (1)",
        ]
    )
    result.add_step("Penghasilan bruto", gross)

    category = table.ter_category(status)
    bracket = table.monthly_ter_rate(category, gross)
    result.metode_tarif = f"TER bulanan kategori {category.value}, tarif {bracket.persen}%"
    result.add_step(
        f"TER bulanan kategori {category.value}",
        catatan=f"tarif {bracket.persen}%, berdasarkan status {status.value}",
    )

    pph = gross * bracket.persen / Decimal(100)
    result.add_step("PPh 21", pph, formula=f"{gross} x {bracket.persen}%")

    result.pph_sebelum_penalti = round_rupiah(pph)
    if punya_npwp:
        result.pph_terutang = result.pph_sebelum_penalti
    else:
        total = round_rupiah(pph * table.faktor_non_npwp)
        result.penalti_non_npwp = total - result.pph_sebelum_penalti
        result.pph_terutang = total
        result.add_step("Tarif lebih tinggi karena tidak ber-NPWP", total)
        result.dasar_hukum.append("UU PPh Pasal 21 ayat (5a)")

    return result
