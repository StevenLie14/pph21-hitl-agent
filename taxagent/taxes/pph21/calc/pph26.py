from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result
from .rates import load_rates
from .rounding import money, round_rupiah


def calc_pph26(
    bruto,
    tahun: int,
    negara_domisili: str = "",
    tarif_p3b_persen=None,
    ada_surat_keterangan_domisili: bool = False,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    gross = money(bruto)
    if gross < 0:
        raise ValueError("jumlah bruto tidak boleh negatif")

    result = PPh21Result(
        jenis_perhitungan="pph26",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.extend(
        ["UU PPh Pasal 26 ayat (1)", "PMK No. 168 Tahun 2023 Pasal 14 ayat (1)"]
    )
    result.add_step("Jumlah bruto", gross)

    rate = table.pph26_persen
    treaty = False

    if tarif_p3b_persen is not None:
        if ada_surat_keterangan_domisili:
            rate = money(tarif_p3b_persen)
            treaty = True
            result.add_step(
                f"Tarif P3B {negara_domisili or 'negara mitra'}",
                catatan=f"{rate}%, berdasarkan Surat Keterangan Domisili yang sah.",
            )
            result.dasar_hukum.append(
                f"Persetujuan Penghindaran Pajak Berganda Indonesia - {negara_domisili or '(negara mitra)'}"
            )
        else:
            result.peringatan.append(
                "Tarif P3B diminta tetapi Surat Keterangan Domisili belum ada, "
                "sehingga tetap dikenakan tarif 20%."
            )

    result.metode_tarif = f"{'Tarif P3B' if treaty else 'Tarif PPh 26'} {rate}%"
    pph = gross * rate / Decimal(100)
    result.add_step("PPh Pasal 26", pph, formula=f"{gross} x {rate}%")

    result.pph_sebelum_penalti = round_rupiah(pph)
    result.pph_terutang = result.pph_sebelum_penalti
    result.asumsi.append(
        "PPh Pasal 26 bersifat final kecuali penerima berubah status menjadi "
        "subjek pajak dalam negeri."
    )
    return result
