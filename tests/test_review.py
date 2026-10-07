import json

import pytest
from test_drafting import PMK_2027

from taxagent.cli import main
from taxagent.taxes.pph21.calc.rates import DATA_DIR
from taxagent.update import assemble_draft, extract_amounts
from taxagent.update.review import apply_decisions, cards, embed_data, render_page, save_json, write_patch


@pytest.fixture()
def draf(tmp_path):
    d = assemble_draft(2027, [extract_amounts(PMK_2027)])
    return json.loads(save_json(d, tmp_path, {"identitas": "PMK 9 Tahun 2027"}).read_text(encoding="utf-8"))


def _isi(k, salah=None):
    return {b["jalur"]: str(salah if salah is not None else b["baru"]) for b in k["berubah"]}


def test_card_requires_only_changed_numbers(draf):
    per = {k["key"]: k for k in cards(draf)}
    assert set(per) == {"ptkp", "biaya_jabatan"}
    jalur = {b["jalur"]: (b["lama"], b["baru"]) for b in per["ptkp"]["berubah"]}
    assert jalur["ptkp.wajib_pajak_sendiri"] == (54000000, 60000000)
    assert all(b["lama"] != b["baru"] for b in per["biaya_jabatan"]["berubah"])
    assert "biaya_jabatan.persen" in {t["jalur"] for t in per["biaya_jabatan"]["tetap"]}


def test_page_hides_draft_and_has_no_inserted_keys(draf):
    daftar, kunci = embed_data(cards(draf), 2, seed=7)
    h = render_page(draf, daftar)
    assert h.count('class="kartu"') == 4 and 'data-jalur="ptkp.wajib_pajak_sendiri"' in h
    assert '<td class="draf">60.000.000</td>' in h and ".draf{display:none}" in h
    assert kunci and all(str(x["benar"]) not in json.dumps(x["cara"]) for x in kunci)
    assert "draf_salah" not in h and "sisip" not in h.lower().replace("sisipan", "")


def test_decision_rechecked_and_inserts_never_enter_patch(draf):
    daftar, kunci = embed_data(cards(draf), 1, seed=3)
    sisip = kunci[0]["id"]
    asli = [k for k in daftar if k["id"] != sisip]
    ptkp = next(k for k in asli if k["key"] == "ptkp")
    bj = next(k for k in asli if k["key"] == "biaya_jabatan")
    kp = {"keputusan": {
        ptkp["id"]: {"keputusan": "terima", "isian": _isi(ptkp)},
        bj["id"]: {"keputusan": "terima", "isian": _isi(bj, salah=1)},
        sisip: {"keputusan": "terima", "isian": _isi(next(k for k in daftar if k["id"] == sisip))},
    }}
    patch, log, r = apply_decisions(draf, daftar, kp, kunci)
    assert set(patch) == {"ptkp"} and patch["ptkp"]["wajib_pajak_sendiri"] == 60000000
    assert r["ditolak_sistem"] == 1 and r["sisipan_lolos"] == 1 and r["sisipan_tertangkap"] == 0
    assert next(x for x in log if x["key"] == "biaya_jabatan")["keputusan"] == "ditolak_sistem"


def test_rupiah_format_and_empty_input_accepted(draf):
    [k] = [x for x in cards(draf) if x["key"] == "ptkp"]
    isian = {b["jalur"]: f"Rp{b['baru']:,}".replace(",", ".") for b in k["berubah"]}
    patch, _, _ = apply_decisions(draf, [k], {"keputusan": {k["id"]: {"keputusan": "terima", "isian": isian}}})
    assert "ptkp" in patch


def test_patch_never_touches_official_data(draf, tmp_path):
    with pytest.raises(ValueError):
        write_patch(draf, {"ptkp": {}}, [], {}, "x", DATA_DIR)
    f = write_patch(draf, {"ptkp": {"wajib_pajak_sendiri": 60000000}}, [], {}, "reviewer", tmp_path / "o")
    assert f[0].name == "patch_tarif_2027.yaml" and "Salin manual" in f[0].read_text(encoding="utf-8")


def test_cli_full_flow(tmp_path, capsys):
    src = tmp_path / "pmk.txt"
    src.write_text(PMK_2027, encoding="utf-8")
    out = tmp_path / "draf"
    main(["draft-rates", "--source", str(src), "--year", "2027", "--output", str(out)])
    f = out / "draf_tarif_2027.json"
    assert f.exists() and "review-draft" in capsys.readouterr().out
    assert main(["review-draft", "--draft", str(f)]) == 0
    assert (out / "review_tarif_2027.html").exists()
    ks = json.loads((out / "review_kunci_2027.json").read_text(encoding="utf-8"))
    kep = {"tahun": 2027, "sidik_draf": ks["sidik"], "reviewer": "uji",
           "keputusan": {k["id"]: {"keputusan": "terima", "isian": _isi(k)} for k in ks["kartu"]}}
    (tmp_path / "k.json").write_text(json.dumps(kep), encoding="utf-8")
    assert main(["review-draft", "--draft", str(f), "--decision", str(tmp_path / "k.json")]) == 0
    assert "biaya_jabatan" in (out / "patch_tarif_2027.yaml").read_text(encoding="utf-8")
    kep["sidik_draf"] = "lain"
    (tmp_path / "k.json").write_text(json.dumps(kep), encoding="utf-8")
    assert main(["review-draft", "--draft", str(f), "--decision", str(tmp_path / "k.json")]) != 0
