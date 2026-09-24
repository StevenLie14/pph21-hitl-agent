from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_TANGGAL = ("Tanggal fakta yang ditanyakan, format YYYY-MM-DD (mis. '2023-11-30'). Kosongkan bila pengguna tidak "
            "menyebut tanggal: dipakai hari ini.")


class PeraturanArgs(BaseModel):
    regulation: str = Field(..., description="Nomor peraturan, mis. 'PMK 168 Tahun 2023', '102/PMK.010/2016', 'UU 7 Tahun 1983'.")
    date: str = Field("", description=_TANGGAL)


class PasalArgs(BaseModel):
    regulation: str = Field(..., description="Nomor peraturan, mis. 'PMK 168 Tahun 2023'.")
    article: str = Field(..., description="Nomor pasal saja, mis. '10' atau '32A'.")
    date: str = Field("", description=_TANGGAL)


class CariTeksArgs(BaseModel):
    query: str = Field(..., description="Pertanyaan atau frasa yang dicari di teks peraturan, mis. 'batas biaya jabatan "
                                        "pegawai tetap' atau 'zakat sebagai pengurang penghasilan'.")
    regulation: str = Field("", description="Batasi pada satu peraturan (opsional), mis. 'PMK 168 Tahun 2023'.")
    date: str = Field("", description=_TANGGAL)
    in_force_only: bool = Field(True, description="True (default): hanya peraturan dan pasal yang berlaku pada tanggal itu. "
                                                  "False hanya untuk pertanyaan sejarah atau aturan lama.")


class FaqArgs(BaseModel):
    query: str = Field(..., description="Kata atau frasa pertanyaan praktis, mis. 'cara membuat bukti potong' atau "
                                        "'PPh 21 DTP karyawan'.")
    date: str = Field("", description=_TANGGAL)


class SkillArgs(BaseModel):
    key: str = Field(..., description="Key data kalkulator: ptkp, biaya_jabatan, biaya_pensiun, tarif_pasal_17, ter_harian, "
                                      "bukan_pegawai, pph_final_pesangon, pph_final_manfaat_pensiun, pph_final_honorarium_pns, natura, dll.")
    date: str = Field("", description=_TANGGAL)


class UsangArgs(BaseModel):
    reason: Literal["tabel_tarif_belum_ada", "peraturan_tidak_dikenal", "dasar_hukum_tidak_berlaku"] = Field(
        ..., description="tabel_tarif_belum_ada: tahun pajak yang ditanyakan sudah berjalan tetapi belum punya tabel "
                         "tarif (tool hitung menolak tahunnya);peraturan_tidak_dikenal: pengguna menyebut peraturan yang tidak ada di graf; "
                         "dasar_hukum_tidak_berlaku: peraturan yang dirujuk data kalkulator sudah dicabut/berakhir menurut graf.")
    regulation: str = Field("", description="Nomor peraturan yang bersangkutan, mis. 'PMK 168 Tahun 2023'. Wajib untuk dua "
                                           "alasan terakhir.")
    fact_date: str = Field("", description=_TANGGAL)
    details: str = Field(..., description="Satu kalimat: apa yang membuatmu menduga data usang (mis. kutipan singkat "
                                             "dari pertanyaan pengguna atau galat tool).")
