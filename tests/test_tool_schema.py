from __future__ import annotations

import pytest

from taxagent.tools import TOOL_SPECS, all_tool_names, call_tool

TIPE_DIIZINKAN = {"string", "integer", "number", "boolean"}


def _skema(args_model) -> dict:
    return args_model.model_json_schema()


@pytest.mark.parametrize("nama,args", [(fn.__name__, a) for fn, a, _ in TOOL_SPECS])
def test_all_arguments_primitive(nama, args):
    skema = _skema(args)
    for field, prop in skema.get("properties", {}).items():
        assert "anyOf" not in prop, (
            f"{nama}.{field} menghasilkan anyOf. Ganti Optional[X] dengan X "
            f"berdefault, misalnya `str = \"\"` atau `float = 0`."
        )
        assert "$ref" not in prop, f"{nama}.{field} memakai model bersarang"
        tipe = prop.get("type")
        assert tipe in TIPE_DIIZINKAN, (
            f"{nama}.{field} bertipe {tipe!r}, di luar {sorted(TIPE_DIIZINKAN)}"
        )


@pytest.mark.parametrize("nama,args", [(fn.__name__, a) for fn, a, _ in TOOL_SPECS])
def test_no_nested_definitions(nama, args):
    skema = _skema(args)
    assert not skema.get("$defs"), f"{nama} punya $defs; ratakan schema-nya"


@pytest.mark.parametrize("nama,args", [(fn.__name__, a) for fn, a, _ in TOOL_SPECS])
def test_every_field_has_description(nama, args):
    skema = _skema(args)
    for field, prop in skema.get("properties", {}).items():
        assert prop.get("description"), f"{nama}.{field} tidak punya deskripsi"


@pytest.mark.parametrize("fn,args,deskripsi", TOOL_SPECS)
def test_every_tool_has_adequate_description(fn, args, deskripsi):
    assert len(deskripsi) > 60, f"deskripsi tool {fn.__name__} terlalu pendek"


def test_tool_names_unique():
    nama = all_tool_names()
    assert len(nama) == len(set(nama))


def test_error_returned_as_data_not_exception():
    hasil = call_tool("calculate_pph21_permanent_monthly", status_ptkp="NGAWUR", masa_pajak=1)
    assert hasil["berhasil"] is False
    assert "galat" in hasil and "saran" in hasil


def test_unavailable_year_also_returned_as_data():
    hasil = call_tool("lookup_ptkp", kawin=True, jumlah_tanggungan=1, tahun_pajak=1999)
    assert hasil["berhasil"] is False
    assert "1999" in hasil["galat"]


def test_legal_basis_rejects_made_up_topic():
    hasil = call_tool("find_legal_basis", topic="pasal_ajaib")
    assert hasil["berhasil"] is False
    assert "tersedia" in hasil["saran"]


def test_legal_basis_valid_topic():
    hasil = call_tool("find_legal_basis", topic="ptkp")
    assert hasil["berhasil"] is True
    assert hasil["rujukan"]


def test_calculation_result_always_has_disclaimer_and_trace():
    hasil = call_tool(
        "calculate_pph21_permanent_monthly",
        gaji_pokok=10_000_000,
        status_ptkp="TK/0",
        masa_pajak=1,
    )
    assert hasil["disclaimer"]
    assert hasil["langkah"], "hasil tanpa jejak langkah membuat agent mengarang narasi"
    assert hasil["dasar_hukum"]
