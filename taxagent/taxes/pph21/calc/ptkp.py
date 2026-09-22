from __future__ import annotations

from decimal import Decimal

from .models import PTKPStatus
from .rates import RateTable, default_year, load_rates
from .rounding import format_rupiah


class InvalidPTKPStatus(ValueError):
    pass


def ptkp_code(
    kawin: bool, jumlah_tanggungan: int, tahun: int | None = None
) -> tuple[PTKPStatus, list[str]]:
    if jumlah_tanggungan < 0:
        raise InvalidPTKPStatus("jumlah tanggungan tidak boleh negatif")

    table = load_rates(tahun if tahun is not None else default_year())
    limit = int(table.ptkp["maksimal_tanggungan"])
    warnings: list[str] = []

    effective = jumlah_tanggungan
    if jumlah_tanggungan > limit:
        effective = limit
        warnings.append(
            f"Jumlah tanggungan {jumlah_tanggungan} melebihi batas {limit} orang; "
            f"yang diperhitungkan hanya {limit} orang."
        )

    prefix = "K" if kawin else "TK"
    return PTKPStatus(f"{prefix}/{effective}"), warnings


def parse_ptkp_status(text: str) -> PTKPStatus:
    clean = text.strip().upper().replace(" ", "").replace("-", "/")
    if "/" not in clean:
        for prefix in ("TK", "K"):
            if clean.startswith(prefix) and clean[len(prefix):].isdigit():
                clean = f"{prefix}/{clean[len(prefix):]}"
                break
    try:
        return PTKPStatus(clean)
    except ValueError as exc:
        valid = ", ".join(s.value for s in PTKPStatus)
        raise InvalidPTKPStatus(
            f"status PTKP '{text}' tidak dikenali. Yang valid: {valid}."
        ) from exc


def annual_ptkp(status: PTKPStatus, tahun: int) -> Decimal:
    return load_rates(tahun).annual_ptkp(status)


def monthly_ptkp(status: PTKPStatus, tahun: int) -> Decimal:
    return annual_ptkp(status, tahun) / Decimal(12)


def ptkp_breakdown(status: PTKPStatus, table: RateTable) -> list[str]:
    code = status.value
    married = code.startswith("K")
    dependants = int(code.split("/")[1])
    lines = [f"diri Wajib Pajak {format_rupiah(table.ptkp['wajib_pajak_sendiri'])}"]
    if married:
        lines.append(f"tambahan kawin {format_rupiah(table.ptkp['tambahan_kawin'])}")
    if dependants:
        lines.append(
            f"{dependants} tanggungan x {format_rupiah(table.ptkp['tambahan_tanggungan'])}"
        )
    return lines
