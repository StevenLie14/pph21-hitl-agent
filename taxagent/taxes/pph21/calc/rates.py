from __future__ import annotations

import functools
from decimal import Decimal
from pathlib import Path

import yaml

from .. import DATA_DIR
from .. import DATA_DIR as PACKAGE_DATA_DIR
from .models import PTKPStatus, TERCategory
from .rounding import money


class TaxYearNotAvailable(LookupError):
    pass


class Bracket:
    __slots__ = ("batas_atas", "persen")

    def __init__(self, batas_atas: int | None, percent) -> None:
        self.batas_atas: Decimal | None = (
            None if batas_atas is None else money(batas_atas)
        )
        self.persen: Decimal = money(percent)

    def __repr__(self) -> str:  # pragma: no cover
        upper = "unbounded" if self.batas_atas is None else f"{self.batas_atas:,}"
        return f"<Bracket up to {upper} = {self.persen}%>"


def _brackets(rows) -> list[Bracket]:
    return [Bracket(r["batas_atas"], r["persen"]) for r in rows]


class RateTable:
    def __init__(self, raw: dict) -> None:
        self._raw = raw
        meta = raw["meta"]
        self.tahun_pajak: int = meta["tahun_pajak"]
        self.berlaku_sejak: str = meta.get("berlaku_sejak", "")
        self.terverifikasi: bool = bool(meta.get("terverifikasi", False))
        self.dasar_hukum: list[str] = list(meta.get("dasar_hukum", []))
        self.dasar_hukum_kunci: dict[str, str] = dict(meta.get("dasar_hukum_kunci") or {})
        self.catatan_verifikasi: str = meta.get("catatan_verifikasi", "")

        self.ptkp = raw["ptkp"]
        self.biaya_jabatan = raw["biaya_jabatan"]
        self.biaya_pensiun = raw["biaya_pensiun"]
        self.pembulatan_pkp: int = int(raw.get("pembulatan_pkp", 1000))
        self.tarif_pasal_17 = _brackets(raw["tarif_pasal_17"])
        self.faktor_non_npwp: Decimal = money(raw["non_npwp"]["faktor"])
        self._kategori_ter = raw["kategori_ter"]
        self._ter_bulanan = {k: _brackets(v) for k, v in raw["ter_bulanan"].items()}
        self.ter_harian = raw["ter_harian"]
        self._ter_harian_lapisan = _brackets(raw["ter_harian"]["lapisan"])
        self.bukan_pegawai = raw["bukan_pegawai"]
        self.natura = {k: money(v) for k, v in raw["natura"].items()}
        self.pph26_persen: Decimal = money(raw["pph26"]["persen"])
        self.final_pesangon = _brackets(raw["pph_final_pesangon"])
        self.final_manfaat_pensiun = _brackets(raw["pph_final_manfaat_pensiun"])
        self.final_honorarium_pns = raw["pph_final_honorarium_pns"]


    def verification_warning(self) -> list[str]:
        if self.terverifikasi:
            return []
        return [
            f"Tabel tarif tahun {self.tahun_pajak} BELUM diverifikasi terhadap "
            f"lampiran peraturan resmi (meta.terverifikasi = false). Angka hasil "
            f"perhitungan belum layak dipakai sebagai rujukan final."
        ]


    def annual_ptkp(self, status: PTKPStatus) -> Decimal:
        code = status.value
        married = code.startswith("K")
        dependants = int(code.split("/")[1])
        amount = money(self.ptkp["wajib_pajak_sendiri"])
        if married:
            amount += money(self.ptkp["tambahan_kawin"])
        amount += money(self.ptkp["tambahan_tanggungan"]) * dependants
        return amount


    def ter_category(self, status: PTKPStatus) -> TERCategory:
        try:
            return TERCategory(self._kategori_ter[status.value])
        except KeyError as exc:  # pragma: no cover
            raise LookupError(
                f"status PTKP {status.value} tidak punya pemetaan kategori TER"
            ) from exc

    def monthly_ter_rate(self, category: TERCategory, monthly_gross) -> Bracket:
        return _find_bracket(self._ter_bulanan[category.value], monthly_gross)

    def monthly_ter_brackets(self, category: TERCategory) -> list[Bracket]:
        return list(self._ter_bulanan[category.value])

    def daily_ter_rate(self, daily_gross) -> Bracket:
        return _find_bracket(self._ter_harian_lapisan, daily_gross)


def _find_bracket(brackets: list[Bracket], amount) -> Bracket:
    amount = money(amount)
    for bracket in brackets:
        if bracket.batas_atas is None or amount <= bracket.batas_atas:
            return bracket
    return brackets[-1]  # pragma: no cover


def calc_progressive(pkp, brackets: list[Bracket]) -> tuple[Decimal, list[tuple[Bracket, Decimal, Decimal]]]:
    if not brackets:
        raise ValueError("lapisan tarif kosong: nilai tarif untuk tahun ini belum diketahui")
    pkp = money(pkp)
    remaining = pkp
    lower = Decimal(0)
    total = Decimal(0)
    breakdown: list[tuple[Bracket, Decimal, Decimal]] = []

    for bracket in brackets:
        if remaining <= 0:
            break
        if bracket.batas_atas is None:
            taxed = remaining
        else:
            taxed = min(remaining, bracket.batas_atas - lower)
            lower = bracket.batas_atas
        if taxed <= 0:
            continue
        tax = taxed * bracket.persen / Decimal(100)
        total += tax
        breakdown.append((bracket, taxed, tax))
        remaining -= taxed

    if remaining > 0:
        raise ValueError("lapisan tarif tidak lengkap: lapisan terakhir harus tanpa batas atas")
    return total, breakdown


@functools.cache
def load_rates(year: int) -> RateTable:
    return RateTable(load_raw(year))


def load_raw(year: int) -> dict:
    return _load_raw(year, seen=frozenset())


def _load_raw(year: int, seen: frozenset) -> dict:
    if year in seen:
        raise ValueError(f"rantai warisi_dari melingkar pada tahun {year}")
    path = DATA_DIR / f"tarif_{year}.yaml"
    if not path.exists():
        available = ", ".join(str(t) for t in available_years()) or "(tidak ada)"
        raise TaxYearNotAvailable(
            f"Tabel tarif untuk tahun pajak {year} belum tersedia. "
            f"Tahun yang tersedia: {available}."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    parent_year = raw.get("meta", {}).get("warisi_dari")
    if parent_year is None:
        return raw

    parent = _load_raw(int(parent_year), seen | {year})
    merged = dict(parent)
    for key, val in raw.items():
        if key == "meta":
            meta = dict(parent.get("meta", {}))
            meta.update(val)
            merged["meta"] = meta
        else:
            merged[key] = val
    return merged


def available_years() -> list[int]:
    years = []
    for p in sorted(DATA_DIR.glob("tarif_*.yaml")):
        try:
            years.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):  # pragma: no cover
            continue
    return years


def default_year() -> int:
    import datetime

    this_year = datetime.date.today().year
    available = available_years()
    if this_year in available:
        return this_year
    return max(available) if available else this_year


def use_data_dir(path: Path | None) -> None:
    global DATA_DIR
    DATA_DIR = PACKAGE_DATA_DIR if path is None else Path(path)
    load_rates.cache_clear()
    load_regulations.cache_clear()


@functools.lru_cache(maxsize=1)
def load_regulations() -> dict:
    path = DATA_DIR / "regulasi.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["topik"]
