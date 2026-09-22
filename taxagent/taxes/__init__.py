from __future__ import annotations

from importlib import import_module, metadata

from ..settings import get_settings
from .base import InvalidArguments, TaxModule, ToolSpec

__all__ = ["BUILTIN", "DEFAULT", "ENTRY_POINT_GROUP", "InvalidArguments", "TaxModule", "ToolSpec", "available", "get"]

BUILTIN = {"pph21": "taxagent.taxes.pph21.module:MODULE"}
ENTRY_POINT_GROUP = "taxagent.taxes"
DEFAULT = "pph21"

_loaded: dict[str, TaxModule] = {}


def _sources() -> dict[str, str]:
    found = dict(BUILTIN)
    for ep in metadata.entry_points(group=ENTRY_POINT_GROUP):
        found.setdefault(ep.name, ep.value)
    return found


def available() -> list[str]:
    return sorted(_sources())


def get(key: str | None = None) -> TaxModule:
    key = key or get_settings().tax or DEFAULT
    if key not in _loaded:
        source = _sources().get(key)
        if source is None:
            raise KeyError(f"unknown tax module '{key}'; available: {available()}")
        module_name, _, attr = source.partition(":")
        obj = getattr(import_module(module_name), attr or "MODULE")
        if not isinstance(obj, TaxModule):
            raise TypeError(f"{source} is {type(obj).__name__}, expected TaxModule")
        _loaded[key] = obj
    return _loaded[key]
