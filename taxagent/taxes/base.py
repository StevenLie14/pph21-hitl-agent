from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

ToolSpec = tuple[Callable[..., dict], "type[BaseModel]", str]


class InvalidArguments(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class TaxModule:
    key: str
    title: str
    data_dir: Path
    calc_dir: Path
    system_prompt: Callable[[], str]
    tool_specs: Callable[[], list[ToolSpec]]
    available_years: Callable[[], list[int]]
    default_year: Callable[[], int]
    load_raw: Callable[[int], dict[str, Any]]
    load_regulations: Callable[[], dict[str, Any]]
    validate_rates: Callable[[dict[str, Any]], None]
    use_data_dir: Callable[[Path | None], None] | None = None
    register_cli: Callable[[Any], None] | None = None
