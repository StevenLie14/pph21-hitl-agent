from __future__ import annotations

from pathlib import Path

from taxagent.evaluation.scorer import contains_key_facts, load_cases
from taxagent.tools import call_tool

DATA = Path(__file__).parents[1] / "taxagent" / "taxes" / "pph21" / "data"


def test_natural_set_loads_and_cites_a_source() -> None:
    cases = load_cases(DATA / "kasus_agent_uji_alami.yaml")
    assert len(cases) == 22
    for case in cases:
        assert case["sumber"].startswith("https://tanyapajak.flazztax.com/")
        if case["perilaku"] == "info":
            assert case["harus_memuat"] and case["dasar"]


def test_natural_set_calculation_keys() -> None:
    keys = {"al-10": "525000", "al-13": "0", "al-16": "16500000", "al-17": "2160000", "al-23": "116850"}
    cases = {c["id"]: c for c in load_cases(DATA / "kasus_agent_uji_alami.yaml")}
    for cid, expected in keys.items():
        result = call_tool(cases[cid]["tool"], **cases[cid]["argumen"])
        assert result["berhasil"] and str(result["pph_terutang"]) == expected, cid


def test_key_facts_accept_alternatives() -> None:
    case = {"harus_memuat": [["5%", "5 persen"], ["6.000.000", "6 juta"]]}
    assert contains_key_facts("biaya jabatan 5 persen, paling banyak rp6.000.000 setahun", case)
    assert not contains_key_facts("biaya jabatan 5%", case)
    assert contains_key_facts("apa saja", {})


def test_original_questions_replace_wording_only(tmp_path) -> None:
    from taxagent.evaluation.scorer import apply_original_questions

    path = tmp_path / "asli.yaml"
    path.write_text("kasus:\n  al-13:\n    pertanyaan: kalimat asli penanya\n", encoding="utf-8")
    cases = load_cases(DATA / "kasus_agent_uji_alami.yaml")
    before = {c["id"]: dict(c) for c in cases}
    assert apply_original_questions(cases, path) == 1
    changed = next(c for c in cases if c["id"] == "al-13")
    assert changed["pertanyaan"] == "kalimat asli penanya" and changed["pertanyaan_asli"]
    assert changed["argumen"] == before["al-13"]["argumen"]
    assert all(c["pertanyaan"] == before[c["id"]]["pertanyaan"] for c in cases if c["id"] != "al-13")


def test_scraper_reads_question_not_author_and_flags_cut_text() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("nq", Path(__file__).parents[1] / "experiments" / "natural_questions.py")
    nq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nq)
    html = """<div id="comment-1" class="wpd-comment-right">
      <div class="wpd-comment-author">Nama Penanya</div><div class="wpd-comment-date">Mei 1, 2025</div>
      <div class="wpd-comment-text"><p>gaji 3jt kena pph ga <span class="wpdiscuz-hellip">...</span>
      <span class="wpdiscuz-readmore">Read more</span></p></div></div>"""
    item = nq.extract(html, {"comment-1": "x"})["x"]
    assert item == {"pertanyaan": "gaji 3jt kena pph ga", "tanggal": "Mei 1, 2025", "terpotong": True}
    assert nq.pages_needed([{"id": "x", "sumber": "https://a/comment-page-2/#comment-1"}]) == {
        "https://a/comment-page-2/": {"comment-1": "x"}}


def test_scraper_redacts_self_introduced_name() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("nq", Path(__file__).parents[1] / "experiments" / "natural_questions.py")
    nq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nq)
    assert nq.redact_names("Selamat sore perkenalkan saya Budi Santoso Putra, saya ingin bertanya") == (
        "Selamat sore perkenalkan saya [nama], saya ingin bertanya")
    assert nq.redact_names("nama saya mau tanya soal thr") == "nama saya mau tanya soal thr"
