from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .rounding import money


class PTKPStatus(str, Enum):
    TK0 = "TK/0"
    TK1 = "TK/1"
    TK2 = "TK/2"
    TK3 = "TK/3"
    K0 = "K/0"
    K1 = "K/1"
    K2 = "K/2"
    K3 = "K/3"


class TERCategory(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class WageScheme(str, Enum):
    HARIAN = "harian"
    MINGGUAN = "mingguan"
    SATUAN = "satuan"
    BORONGAN = "borongan"
    BULANAN = "bulanan"


class FinalIncomeType(str, Enum):
    PESANGON = "pesangon"
    MANFAAT_PENSIUN = "manfaat_pensiun"
    HONORARIUM_PNS = "honorarium_pns"


class Article17DirectType(str, Enum):
    PESERTA_KEGIATAN = "peserta_kegiatan"
    PESERTA_PENSIUN_PEGAWAI = "peserta_pensiun_pegawai"
    MANTAN_PEGAWAI = "mantan_pegawai"


class IncomeComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gaji_pokok: Decimal = Decimal(0)
    tunjangan_tetap: Decimal = Decimal(0)
    tunjangan_tidak_tetap: Decimal = Decimal(0)
    lembur: Decimal = Decimal(0)
    bonus_thr_komisi: Decimal = Decimal(0)
    tunjangan_pph: Decimal = Decimal(0)
    premi_jkk_dibayar_pemberi_kerja: Decimal = Decimal(0)
    premi_jkm_dibayar_pemberi_kerja: Decimal = Decimal(0)
    premi_bpjs_kesehatan_dibayar_pemberi_kerja: Decimal = Decimal(0)
    natura_kena_pajak: Decimal = Decimal(0)
    penghasilan_lain: Decimal = Decimal(0)

    iuran_jht_dibayar_pemberi_kerja: Decimal = Decimal(0)
    iuran_jp_dibayar_pemberi_kerja: Decimal = Decimal(0)

    iuran_pensiun_dibayar_pegawai: Decimal = Decimal(0)
    iuran_jht_dibayar_pegawai: Decimal = Decimal(0)
    iuran_jp_dibayar_pegawai: Decimal = Decimal(0)
    zakat_via_pemberi_kerja: Decimal = Decimal(0)

    iuran_bpjs_kesehatan_dibayar_pegawai: Decimal = Decimal(0)

    @field_validator("*", mode="before")
    @classmethod
    def _to_decimal(cls, v):
        return money(v) if v is not None else Decimal(0)

    @field_validator("*", mode="after")
    @classmethod
    def _non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("komponen penghasilan tidak boleh negatif")
        return v

    def bruto(self) -> Decimal:
        return (
            self.gaji_pokok
            + self.tunjangan_tetap
            + self.tunjangan_tidak_tetap
            + self.lembur
            + self.bonus_thr_komisi
            + self.tunjangan_pph
            + self.premi_jkk_dibayar_pemberi_kerja
            + self.premi_jkm_dibayar_pemberi_kerja
            + self.premi_bpjs_kesehatan_dibayar_pemberi_kerja
            + self.natura_kena_pajak
            + self.penghasilan_lain
        )

    def deductions_excluding_job_expense(self) -> Decimal:
        return (
            self.iuran_pensiun_dibayar_pegawai
            + self.iuran_jht_dibayar_pegawai
            + self.iuran_jp_dibayar_pegawai
            + self.zakat_via_pemberi_kerja
        )

    def scaled(self, factor: int) -> IncomeComponents:
        data = {
            k: v * Decimal(factor)
            for k, v in self.model_dump().items()
        }
        return IncomeComponents(**data)


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    formula: str = ""
    nilai: Decimal | None = None
    catatan: str = ""


class PPh21Result(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jenis_perhitungan: str
    tahun_pajak: int
    masa_pajak: int | None = None

    penghasilan_bruto: Decimal = Decimal(0)
    dasar_pengenaan_pajak: Decimal | None = None
    metode_tarif: str = ""

    pph_sebelum_penalti: Decimal = Decimal(0)
    penalti_non_npwp: Decimal = Decimal(0)
    pph_terutang: Decimal = Decimal(0)
    pph_ditanggung_pemerintah: Decimal = Decimal(0)
    kode_objek_pajak: str = ""

    langkah: list[Step] = Field(default_factory=list)
    dasar_hukum: list[str] = Field(default_factory=list)
    asumsi: list[str] = Field(default_factory=list)
    peringatan: list[str] = Field(default_factory=list)

    def add_step(self, label: str, nilai=None, formula: str = "", catatan: str = "") -> None:
        self.langkah.append(
            Step(
                label=label,
                formula=formula,
                nilai=money(nilai) if nilai is not None else None,
                catatan=catatan,
            )
        )
