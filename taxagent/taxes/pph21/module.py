from __future__ import annotations

from ..base import TaxModule, ToolSpec
from . import DATA_DIR
from .calc import rates


def _system_prompt() -> str:
    from .prompt import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def _tool_specs() -> list[ToolSpec]:
    from .tools import TOOL_SPECS

    return TOOL_SPECS


def _register_cli(sub) -> None:
    from .cli import register

    register(sub)


def _validate_rates(raw: dict) -> None:
    rates.RateTable(raw)


MODULE = TaxModule(
    key="pph21",
    title="PPh Pasal 21",
    data_dir=DATA_DIR,
    calc_dir=DATA_DIR.parent / "calc",
    system_prompt=_system_prompt,
    tool_specs=_tool_specs,
    available_years=rates.available_years,
    default_year=rates.default_year,
    load_raw=rates.load_raw,
    load_regulations=rates.load_regulations,
    validate_rates=_validate_rates,
    use_data_dir=rates.use_data_dir,
    register_cli=_register_cli,
)
