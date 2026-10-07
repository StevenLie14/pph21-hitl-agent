from __future__ import annotations

INCOMING_TYPES = ("MENCABUT", "MENCABUT_SEBAGIAN", "MENGUBAH")
_WEAK = {"tanpa_bukti": "klaim JDIH tanpa bukti teks", "belum_dicek": "klaim JDIH belum dicek ke teks"}


def status_from_graph(regulation: str, until_year: int | None = None) -> list[tuple[str, str]] | None:
    from ..monitor.identity import canon_id
    from ..tools import regulation_graph as G

    r = G.amendment_chain(regulation=regulation)
    if not r.get("berhasil"):
        return None
    result = []
    for x in r.get("diubah_atau_dicabut_oleh", []):
        rel_type = (x.get("jenis") or "").upper()
        if rel_type not in INCOMING_TYPES or x.get("peraturan") == r.get("peraturan"):
            continue
        ident = canon_id(x.get("peraturan") or "")
        if until_year is not None and (ident is None or ident.year >= until_year):
            continue
        name = x["peraturan"] + (f" ({_WEAK[x['bukti']]})" if x.get("bukti") in _WEAK else "")
        result.append((rel_type, name))
    return result
