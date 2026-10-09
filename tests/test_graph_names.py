from taxagent.graph_names import AMENDMENT_RELATIONSHIPS, INDEXES, LABELS, PROPERTIES, RELATIONSHIPS, graph_props


def test_new_names_never_reuse_an_old_name():
    assert not set(PROPERTIES.values()) & set(PROPERTIES)
    assert not set(LABELS.values()) & set(LABELS)
    assert not set(RELATIONSHIPS.values()) & (set(RELATIONSHIPS) | set(AMENDMENT_RELATIONSHIPS))
    assert not {new for new, _ in INDEXES.values()} & set(INDEXES)


def test_graph_props_translates_known_keys_and_keeps_the_rest():
    assert graph_props({"kunci": "PMK 168 Tahun 2023", "teks_cari": "x", "stub": False, "url": "u"}) == \
        {"key": "PMK 168 Tahun 2023", "search_text": "x", "stub": False, "url": "u"}


def test_full_graph_plan_writes_only_english_property_names():
    from taxagent.corpus.full_graph import merge_relations, plan

    rel = merge_relations([], [{"dari": "PMK 168 Tahun 2023", "jenis": "mencabut", "ke": "PMK 252 Tahun 2008",
                                "kelas": "eksplisit", "kutipan": "dicabut", "pasal": "Pasal 24"}], {})
    r = plan([{"kunci": "PMK 168 Tahun 2023", "judul": "PMK", "mulai": "2024-01-01", "punya_teks": True}], rel,
             [{"id": "PMK 168 Tahun 2023#0", "peraturan": "PMK 168 Tahun 2023", "urutan": 0, "label_pasal": "Pasal 1",
               "teks": "t", "teks_cari": "t", "offset_awal": 0, "offset_akhir": 1, "halaman": 1}],
             {"ptkp": {"deskripsi": "d", "istilah": ["PTKP"]}}, [("PMK 168 Tahun 2023", "ptkp", ["7"])], {"commit": "x"})
    written = [*r.regulations.values(), *r.relations.values(), *r.chunks, *r.parameters.values()]
    left = {k for d in written for k in graph_props(d) if k in PROPERTIES}
    assert not left
    assert {k for d in written for k in d} - {"dari", "ke", "stub", "url", "id", "model"} <= set(PROPERTIES)
