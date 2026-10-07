from __future__ import annotations

from decimal import Decimal

from taxagent.cli.drafting import _merge_llm, _source_name
from taxagent.update.llm import LLMResult

D = Decimal


def test_first_source_used_as_is():
    h = LLMResult(values={"ptkp.wajib_pajak_sendiri": D(54000000)})
    assert _merge_llm(None, h, set()) is h


def test_same_numbers_across_sources_kept_and_new_added():
    a = LLMResult(values={"ptkp.wajib_pajak_sendiri": D(54000000)})
    b = LLMResult(values={"ptkp.wajib_pajak_sendiri": D(54000000), "ptkp.tambahan_kawin": D(4500000)})
    g = _merge_llm(a, b, set())
    assert g.values == {"ptkp.wajib_pajak_sendiri": D(54000000), "ptkp.tambahan_kawin": D(4500000)}
    assert g.dropped == []


def test_numbers_differing_across_sources_dropped_and_not_reappearing():
    konflik: set[str] = set()
    a = LLMResult(values={"biaya_jabatan.persen": D(5)})
    g = _merge_llm(a, LLMResult(values={"biaya_jabatan.persen": D(6)}), konflik)
    assert "biaya_jabatan.persen" not in g.values and konflik == {"biaya_jabatan.persen"}
    assert "sumber berbeda (5 dan 6)" in g.dropped[0]
    g = _merge_llm(g, LLMResult(values={"biaya_jabatan.persen": D(5)}), konflik)
    assert "biaya_jabatan.persen" not in g.values


def test_invalid_answer_from_one_source_invalidates_merge():
    g = _merge_llm(LLMResult(), LLMResult(valid=False, dropped=["x: kutipan tidak ada di teks"]), set())
    assert g.valid is False and g.dropped == ["x: kutipan tidak ada di teks"]


def test_source_name_full_url_file_name_only():
    assert _source_name("https://jdih.kemenkeu.go.id/a/b.pdf") == "https://jdih.kemenkeu.go.id/a/b.pdf"
    assert _source_name("C:/data/teks/PMK_168.txt") == "PMK_168.txt"
