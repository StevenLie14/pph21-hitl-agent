from __future__ import annotations

from decimal import Decimal

from .models import PPh21Result

IKN_LAST_YEAR = 2035
IKN_FIRST_YEAR = 2023


def apply_ikn_facility(h: PPh21Result, punya_npwp: bool) -> PPh21Result:
    if h.tahun_pajak > IKN_LAST_YEAR:
        raise ValueError(f"fasilitas PPh 21 DTP IKN hanya berlaku sampai masa pajak Desember {IKN_LAST_YEAR} "
                         "(PMK 28/2024 Pasal 138); hitung tanpa fasilitas_ikn")
    if h.tahun_pajak < IKN_FIRST_YEAR:
        raise ValueError(f"fasilitas PPh 21 DTP IKN baru diatur mulai {IKN_FIRST_YEAR} (PP 12/2023)")
    if not punya_npwp:
        raise ValueError("fasilitas PPh 21 DTP IKN mensyaratkan pegawai ber-NPWP yang terdaftar di KPP wilayah IKN "
                         "(PMK 28/2024 Pasal 123 ayat (3) huruf c); tanpa NPWP hitung tanpa fasilitas_ikn")
    h.pph_ditanggung_pemerintah = max(h.pph_terutang, Decimal(0))
    h.jenis_perhitungan += "_ikn"
    h.metode_tarif += ", PPh 21 ditanggung pemerintah dan bersifat final (IKN)"
    h.add_step("PPh 21 ditanggung pemerintah (fasilitas IKN)", h.pph_ditanggung_pemerintah,
               catatan="Dibayar tunai oleh pemberi kerja dan tidak dihitung sebagai penghasilan pegawai.")
    h.add_step("PPh 21 yang dipotong dari penghasilan pegawai", Decimal(0))
    h.dasar_hukum.extend(["PP No. 12 Tahun 2023 Pasal 50",
                          "PMK No. 28 Tahun 2024 Pasal 123 dan Pasal 129",
                          "PMK No. 28 Tahun 2024 Pasal 138"])
    h.asumsi.append(
        "Fasilitas IKN berlaku bila pemberi kerja tertentu sudah mendapat persetujuan pemanfaatan dan "
        "menyampaikan laporan realisasi, serta pegawai bertempat tinggal di IKN dan NPWP-nya terdaftar di KPP "
        "wilayah IKN. Masa yang laporan realisasinya tidak disampaikan tidak mendapat fasilitas: PPh-nya disetor "
        "pemberi kerja (kode 21-100-37). Tidak berlaku untuk honor pejabat negara, PNS, TNI, atau POLRI dari "
        "APBN/APBD yang PPh-nya sudah ditanggung pemerintah."
    )
    h.asumsi.append("Penghasilan ini dilaporkan pegawai di SPT Tahunan sebagai penghasilan yang dikenai PPh final.")
    return h
