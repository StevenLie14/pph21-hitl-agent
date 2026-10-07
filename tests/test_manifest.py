import pytest

from taxagent.update.manifest import from_dict, load


def test_pph21_manifest_complete():
    m = load()
    assert m.effective_mode == "tahun_pajak" and m.number_scope[0] == "ptkp"
    assert m.range_for("tarif_pasal_17[3].persen") == m.range_for("tarif_pasal_17[].persen")
    assert m.range_for("ptkp.tidak_ada") is None
    pola = m.groups["tarif_pasal_17"].field_pattern()
    assert pola.match("tarif_pasal_17[4].batas_atas") and not pola.match("tarif_pasal_17[4].lain")
    assert "lapisan[i]" not in m.groups["ter_harian"].catalog()


@pytest.mark.parametrize("rusak, pesan", [
    ({"mode_berlaku": "bulanan"}, "mode_berlaku"),
    ({"kelompok": {"x": {"istilah": ["x"], "field": {"a": {"jenis": "kg", "rentang": [0, 1], "arti": "a"}}}}}, "jenis"),
    ({"kelompok": {"x": {"istilah": ["x"], "field": {"a": {"jenis": "persen", "arti": "a"}}}}}, "rentang"),
    ({"kelompok": {"x": {"istilah": ["x"], "field": {"a": {"jenis": "persen", "rentang": [0, 1]}}}}}, "arti"),
    ({"kelompok": {"x": {"istilah": ["x"], "konsistensi": [{"jenis": "eval"}],
                         "field": {"a": {"jenis": "persen", "rentang": [0, 1], "arti": "a"}}}}}, "konsistensi"),
])
def test_broken_manifest_rejected(rusak, pesan):
    data = {"skill": "uji", "mode_berlaku": "tanggal", "berkas_data": "x.yaml", "prompt_pembuka": "Anda", **rusak}
    with pytest.raises(ValueError, match=pesan):
        from_dict(data)


def test_pilot_manifest_draft_valid_structure():
    import yaml

    from taxagent.update.manifest import SKILL_DIR

    for f in sorted((SKILL_DIR / "draf").glob("*.yaml")):
        m = from_dict(yaml.safe_load(f.read_text(encoding="utf-8")))
        assert m.effective_mode == "tanggal" and m.groups, f.name
