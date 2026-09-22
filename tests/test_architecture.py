from __future__ import annotations

import ast
from pathlib import Path

import pytest

from taxagent import taxes
from taxagent.paths import PACKAGE_DIR
from taxagent.taxes import TaxModule

ALLOWED: set[str] = set()


def _imports(path: Path) -> set[str]:
    rel = path.relative_to(PACKAGE_DIR.parent).with_suffix("")
    package = rel.parts[:-1] if rel.name != "__init__" else rel.parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            base = list(package)[: len(package) - (node.level - 1)] if node.level else []
            mod = ".".join([*base, *(node.module.split(".") if node.module else [])])
            found |= {mod} | {f"{mod}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
    return found


def test_generic_layers_do_not_import_a_tax_module_directly():
    offenders = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        rel = path.relative_to(PACKAGE_DIR).as_posix()
        if rel.startswith("taxes/") or rel in ALLOWED:
            continue
        bad = sorted(m for m in _imports(path) if m.startswith("taxagent.taxes.") and m.split(".")[2] not in ("base",))
        bad = [m for m in bad if m.split(".")[2] in taxes.BUILTIN]
        if bad:
            offenders.append(f"{rel}: {bad}")
    assert offenders == []


def test_registry_returns_the_pph21_module_by_default(monkeypatch):
    monkeypatch.delenv("TAXAGENT_TAX", raising=False)
    m = taxes.get()
    assert isinstance(m, TaxModule) and m.key == "pph21"
    assert m is taxes.get("pph21")
    assert (m.data_dir / "regulasi.yaml").exists() and (m.calc_dir / "rates.py").exists()
    assert m.default_year() in m.available_years()
    assert "PPh" in m.system_prompt() and m.tool_specs()


def test_unknown_tax_module_is_an_error():
    with pytest.raises(KeyError, match="unknown tax module 'ppn'"):
        taxes.get("ppn")


def test_validate_rates_rejects_a_table_the_engine_cannot_load():
    m = taxes.get()
    m.validate_rates(m.load_raw(m.default_year()))
    with pytest.raises(Exception):  # noqa: B017
        m.validate_rates({"meta": {}})


def test_pph21_contributes_its_cli_commands():
    import argparse

    m = taxes.get()
    sub = argparse.ArgumentParser().add_subparsers()
    m.register_cli(sub)
    assert {"rates", "ptkp", "calculate", "tool"} <= set(sub.choices)
