from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from taxagent.tools import call_tool

FIXTURE = Path(__file__).parent / "fixtures" / "contoh_resmi.yaml"
_DATA = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
SEMUA = (_DATA.get("kasus") or []) + (_DATA.get("kasus_resmi") or [])
RESMI = _DATA.get("kasus_resmi") or []


def _id(kasus: dict) -> str:
    return f"{kasus['sumber']}::{kasus['nama']}"


@pytest.mark.parametrize("kasus", SEMUA, ids=[_id(k) for k in SEMUA])
def test_cases(kasus: dict) -> None:
    hasil = call_tool(kasus["tool"], **kasus["argumen"])
    assert hasil["berhasil"], hasil.get("galat")

    for field, diharapkan in kasus["harapan"].items():
        aktual = hasil[field]
        assert str(aktual) == str(diharapkan), (
            f"{kasus['nama']}: field '{field}' seharusnya {diharapkan}, ternyata {aktual}"
        )


def test_every_case_cites_source() -> None:
    for kasus in SEMUA:
        assert kasus.get("sumber"), f"kasus '{kasus.get('nama')}' tidak menyebut sumber"


def test_official_case_reminder_still_empty() -> None:
    if not RESMI:
        pytest.skip(
            "kasus_resmi masih kosong. Salin contoh perhitungan dari lampiran "
            "peraturan resmi ke fixtures/contoh_resmi.yaml untuk memperoleh "
            "bukti kebenaran terhadap regulasi."
        )


def test_official_test_set_matches_official_examples() -> None:
    path = Path(__file__).parents[1] / "taxagent" / "taxes" / "pph21" / "data" / "kasus_agent_uji_resmi.yaml"
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))["kasus"]
    official = [(k["tool"], k["argumen"]) for k in RESMI]
    assert len(cases) == 19
    for case in cases:
        assert (case["tool"], case["argumen"]) in official, case["id"]
