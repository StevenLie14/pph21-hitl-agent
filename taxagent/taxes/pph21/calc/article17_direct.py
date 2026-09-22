from __future__ import annotations

from .models import Article17DirectType, PPh21Result
from .rates import calc_progressive, load_rates
from .rounding import money, round_rupiah

_LEGAL_BASIS = {
    Article17DirectType.PESERTA_KEGIATAN: (
        "PMK No. 168 Tahun 2023 Pasal 12 ayat (6) dan Pasal 16 ayat (4)"
    ),
    Article17DirectType.PESERTA_PENSIUN_PEGAWAI: (
        "PMK No. 168 Tahun 2023 Pasal 12 ayat (7) dan Pasal 16 ayat (5)"
    ),
    Article17DirectType.MANTAN_PEGAWAI: (
        "PMK No. 168 Tahun 2023 Pasal 12 ayat (8) dan Pasal 16 ayat (6)"
    ),
}

_LABEL = {
    Article17DirectType.PESERTA_KEGIATAN: "Peserta Kegiatan",
    Article17DirectType.PESERTA_PENSIUN_PEGAWAI: "Peserta program pensiun (masih Pegawai)",
    Article17DirectType.MANTAN_PEGAWAI: "Mantan Pegawai",
}


def calc_article17_direct(
    jenis: Article17DirectType,
    bruto,
    tahun: int,
    punya_npwp: bool = True,
    masa_pajak: int | None = None,
) -> PPh21Result:
    table = load_rates(tahun)
    gross = money(bruto)
    if gross < 0:
        raise ValueError("penghasilan bruto tidak boleh negatif")

    result = PPh21Result(
        jenis_perhitungan=f"pasal17_langsung_{jenis.value}",
        tahun_pajak=tahun,
        masa_pajak=masa_pajak,
        penghasilan_bruto=gross,
        dasar_pengenaan_pajak=gross,
        metode_tarif="Tarif Pasal 17 langsung atas bruto",
    )
    result.peringatan.extend(table.verification_warning())
    result.dasar_hukum.append(_LEGAL_BASIS[jenis])
    result.add_step(f"Penghasilan bruto ({_LABEL[jenis]})", gross)

    pph, breakdown = calc_progressive(gross, table.tarif_pasal_17)
    for bracket, taxed, tax in breakdown:
        result.add_step(f"Lapisan {bracket.persen}%", tax, formula=f"{taxed} x {bracket.persen}%")
    result.add_step("PPh 21", pph)

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
