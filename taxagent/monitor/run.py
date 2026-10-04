from __future__ import annotations

import datetime as _dt
import re
from dataclasses import asdict, dataclass, field

from .classify import Classification, Watchlist, classify, load_watchlist
from .classify_llm import LLMClassification
from .enrichment import Enrichment, Fetcher, enrich, page_from_id
from .identity import RegulationId, from_slug
from .jdih import JDIHPage
from .resilience import check_canaries, check_stale, relation_fingerprint
from .sources import FeedDocument
from .storage import ImpactNote, MonitorState

CODE_NONE = 0
CODE_FINDINGS = 1
CODE_WARNING = 2
CODE_FAILED = 3

BPK_SITEMAP_URL = "https://peraturan.bpk.go.id/sitemap-peraturan-{tahun}.xml"
BPK_TYPES = {"UU", "PERPPU", "PP", "PMK"}
BPK_GRACE_DAYS = 7


@dataclass
class MonitorResult:
    exit_code: int
    new_documents: list[FeedDocument] = field(default_factory=list)
    new_notes: list[ImpactNote] = field(default_factory=list)
    ignored: list[tuple[FeedDocument, Classification]] = field(default_factory=list)
    dropped_articles: int = 0
    failed_enrichments: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: str | None = None
    first_run: bool = False
    watchlist_checked: bool = False
    bpk_checked: bool = False
    canary_checked: bool = False
    llm_called: int = 0
    llm_failed: int = 0
    llm_promoted: int = 0

    def set_code(self) -> None:
        if self.errors:
            self.exit_code = CODE_FAILED
        elif self.new_notes:
            self.exit_code = CODE_FINDINGS
        elif self.warnings:
            self.exit_code = CODE_WARNING
        else:
            self.exit_code = CODE_NONE


def fail(message: str) -> MonitorResult:
    return MonitorResult(exit_code=CODE_FAILED, errors=message)


def _days_since(iso: str | None, now: str) -> float | None:
    if not iso:
        return None
    a = _dt.datetime.fromisoformat(iso[:19])
    b = _dt.datetime.fromisoformat(now[:19])
    return (b - a).total_seconds() / 86400


def _raise_level(k: Classification, p: Enrichment, wl: Watchlist) -> None:
    rank = {"dasar": 0, "fasilitas": 1, "prosedural": 2, "perlu_ditinjau": 3, "tidak_relevan": 4}
    for ident, kind in p.outgoing_relations():
        entry = wl.find(ident)
        if entry is None:
            continue
        if rank[entry.role] < rank[k.category]:
            k.category = entry.role
        k.reasons.append(f"teks/relasi JDIH: {kind.replace('_', ' ')} {ident} (watchlist, {entry.role})")
        if entry.role != "fasilitas":
            for key in entry.governs:
                if key not in k.affected_keys:
                    k.affected_keys.append(key)
        for trigger in entry.triggers:
            if str(trigger) not in k.triggers:
                k.triggers.append(str(trigger))
        if str(ident) not in k.related_ids:
            k.related_ids.append(str(ident))
    if k.category == "fasilitas":
        k.affected_keys = []


def _fill_enrichment(c: ImpactNote, p: Enrichment) -> None:
    c.galat_pengayaan = list(p.error)
    c.selisih = list(p.discrepancies)
    c.url_teks = p.text_url
    c.sumber_teks = p.text_source
    if p.page:
        c.relasi_portal = [
            {"arah": r.arah, "jenis_efek": r.jenis_efek, "nomor": r.nomor, "kode": r.kode}
            for r in p.page.relasi
        ]
        outgoing = [r for r in p.page.relasi if r.arah == "keluar" and r.tgl_mulai_berlaku]
        c.mulai_berlaku_metadata = outgoing[0].tgl_mulai_berlaku if outgoing else None
        c.ditetapkan = c.ditetapkan or p.page.tgl_penetapan
        c.diundangkan = c.diundangkan or p.page.tgl_pengundangan
    if p.text:
        t = p.text
        c.ditetapkan = t.enacted or c.ditetapkan
        c.diundangkan = t.promulgated or c.diundangkan
        c.mulai_berlaku_teks = t.mulai_berlaku_tanggal or t.in_force_from
        c.berlaku_untuk = list(t.applies_to)
        c.retroaktif = t.retroaktif
        c.dicabut_teks = [asdict(x) | {"identitas": str(x.identitas)} for x in t.revokes]
        c.diubah_teks = [str(x) for x in t.amends if x not in t.amends_intermediate]
        c.pasal_terdampak = [f"{x.bagian} {x.identitas}" for x in t.revokes if x.sebagian]
        c.pasal_terdampak += [f"PASAL {', '.join(p)} {i} (diubah)" for i, p in t.amended_articles.items()]


def _note(d_id, ident_text, title, subject, date, timestamp, k: Classification, source: str) -> ImpactNote:
    return ImpactNote(
        id_dokumen=d_id,
        identitas=ident_text,
        judul=title,
        perihal=subject,
        tanggal_feed=date,
        first_seen=timestamp,
        kategori=k.category,
        alasan=list(k.reasons),
        key_terdampak=list(k.affected_keys),
        id_terkait=list(k.related_ids),
        pemicu=list(k.triggers),
        sumber=source,
    )


def _already_noted(state: MonitorState, ident: str) -> bool:
    return any(c.identitas == ident for c in state.catatan)


def check_watchlist(
    state: MonitorState, wl: Watchlist, fetch: Fetcher, timestamp: str, result: MonitorResult
) -> dict[str, JDIHPage]:
    read_pages: dict[str, JDIHPage] = {}
    for e in wl.regulations:
        key = str(e.identity)
        found = page_from_id(e.identity, fetch)
        if found is None:
            result.warnings.append(f"halaman JDIH untuk peraturan watchlist {key} tidak ditemukan")
            continue
        _, page = found
        read_pages[key] = page
        current = sorted({f"{r.arah}|{r.jenis_efek}|{r.identitas or r.nomor}" for r in page.relasi})
        old = state.relasi_watchlist.get(key)
        state.relasi_watchlist[key] = current
        if old is None:
            continue
        for line in sorted(set(current) - set(old)):
            direction, kind, counterpart = line.split("|", 2)
            if direction != "masuk" or _already_noted(state, counterpart):
                continue
            k = Classification(
                category=e.role,
                reasons=[f"JDIH mencatat {key} {kind.replace('_', ' ')} oleh {counterpart}"],
                affected_keys=list(e.governs) if e.role != "fasilitas" else [],
                related_ids=[key],
                triggers=[str(p) for p in e.triggers],
            )
            c = _note(page.url, counterpart, counterpart, "", "", timestamp, k, "jdih_relasi_watchlist")
            state.catatan.append(c)
            result.new_notes.append(c)
    state.watchlist_terakhir = timestamp
    result.watchlist_checked = True
    return read_pages


def run_canaries(state: MonitorState, pages: dict[str, JDIHPage], result: MonitorResult) -> None:
    canary_failures = check_canaries(pages)
    result.canary_checked = True
    if canary_failures:
        result.errors = "kanari gagal (parser JDIH tidak lagi membaca relasi yang pasti ada): " + "; ".join(canary_failures)
        return
    fingerprint = relation_fingerprint(pages)
    if state.kanari_sidik and fingerprint != state.kanari_sidik:
        added = sorted(set(fingerprint) - set(state.kanari_sidik))
        removed = sorted(set(state.kanari_sidik) - set(fingerprint))
        result.warnings.append(
            f"struktur JSON relasi JDIH berubah (kunci baru: {added or '-'}, hilang: {removed or '-'}); kanari masih lolos"
        )
    state.kanari_sidik = fingerprint


def bpk_sitemap_ids(xml: str) -> list[tuple[RegulationId, str]]:
    result = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
        slug = loc.rstrip("/").rsplit("/", 1)[-1]
        ident = from_slug(slug)
        if ident and ident.kind in BPK_TYPES:
            result.append((ident, loc))
    return result


def check_bpk(state: MonitorState, wl: Watchlist, fetch: Fetcher, timestamp: str, result: MonitorResult) -> None:
    year = int(timestamp[:4])
    try:
        xml = fetch(BPK_SITEMAP_URL.format(tahun=year)).decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"sitemap BPK {year} tidak bisa diambil: {exc}")
        return
    entries = bpk_sitemap_ids(xml)
    if not entries:
        result.warnings.append(f"sitemap BPK {year} tidak memuat UU/PP/PMK (format berubah?)")
        return
    baseline = state.bpk_terakhir is None
    seen = state.seen_ids()
    for ident, loc in entries:
        key = str(ident)
        if key in state.bpk_dilihat:
            continue
        state.bpk_dilihat[key] = timestamp
        if not baseline and key not in seen:
            state.bpk_tertunda[key] = loc

    for key, loc in list(state.bpk_tertunda.items()):
        if key in seen:
            del state.bpk_tertunda[key]
            continue
        days = _days_since(state.bpk_dilihat.get(key), timestamp)
        if days is None or days < BPK_GRACE_DAYS:
            continue
        del state.bpk_tertunda[key]
        ident = from_slug(loc.rstrip("/").rsplit("/", 1)[-1])
        found = page_from_id(ident, fetch) if ident else None
        if found is None:
            k = Classification("perlu_ditinjau", [f"ada di sitemap BPK ({loc}) {BPK_GRACE_DAYS}+ hari, tidak ditemukan di JDIH"])
            title = key
        else:
            slug, page = found
            k = classify(page.nomor, page.judul, ident, wl)
            if not k.needs_review:
                continue
            k.reasons.append(f"tidak muncul di feed JDIH dalam {BPK_GRACE_DAYS} hari sejak ada di sitemap BPK")
            title = page.nomor
            state.dilihat[page.url] = {"first_seen": timestamp, "judul": page.nomor, "identitas": key, "sumber": "bpk"}
        c = _note(loc, key, title, "", "", timestamp, k, "bpk_sitemap")
        state.catatan.append(c)
        result.new_notes.append(c)
    state.bpk_terakhir = timestamp
    result.bpk_checked = True


def _merge_llm_opinion(k: Classification, llm: LLMClassification, result: MonitorResult) -> None:
    result.llm_called += 1
    if not llm.valid:
        result.llm_failed += 1
    elif not k.needs_review and llm.category != "tidak_relevan":
        k.category = llm.category
        k.reasons.append(f"LLM + teks: {llm.reason}")
        if k.category == "fasilitas":
            k.affected_keys = []
        result.llm_promoted += 1
    elif k.needs_review:
        k.reasons.append(f"pendapat LLM + teks: {llm.category} ({llm.reason})")


def run(
    documents: list[FeedDocument],
    state: MonitorState,
    watchlist: Watchlist | None = None,
    now: str | None = None,
    fetch: Fetcher | None = None,
    watchlist_check: bool = False,
    bpk_check: bool = False,
    stale_check: bool = False,
    llm_judge=None,
    graph=None,
    impact_client=None,
    ocr=None,
) -> MonitorResult:
    wl = watchlist or load_watchlist()
    timestamp = now or _dt.datetime.now().isoformat(timespec="seconds")
    result = MonitorResult(exit_code=CODE_NONE, first_run=state.is_empty)

    for d in documents:
        if d.id in state.dilihat:
            continue
        state.dilihat[d.id] = {
            "first_seen": timestamp,
            "judul": d.title,
            "tanggal_feed": d.date,
            "identitas": str(d.identity) if d.identity else None,
        }
        if d.artikel:
            result.dropped_articles += 1
            continue
        result.new_documents.append(d)
        k = classify(d.title, d.subject, d.identity, wl)
        p = None
        if fetch and (k.needs_review or not result.first_run):
            p = enrich(d.slug, fetch, d.identity, ocr)
            if p.error and not p.text:
                result.failed_enrichments += 1
            _raise_level(k, p, wl)
        ident_text = str(d.identity) if d.identity else d.title
        llm: LLMClassification | None = None
        if llm_judge and p and p.raw_text:
            llm = llm_judge(ident_text, d.title, d.subject, p.raw_text)
            _merge_llm_opinion(k, llm, result)
        if not k.needs_review:
            result.ignored.append((d, k))
            continue
        c = _note(d.id, ident_text, d.title, d.subject, d.date, timestamp, k, "jdih_feed")
        if p:
            _fill_enrichment(c, p)
        if llm is not None:
            c.pendapat_llm = {"kategori": llm.category, "alasan": llm.reason, "valid": llm.valid}
        if graph is not None and p and p.raw_text:
            from .impact import monitor_impact

            facility = k.category == "fasilitas" or bool(llm and llm.valid and llm.category == "fasilitas")
            c.dampak = monitor_impact(d.title, d.subject, d.identity, p.raw_text, wl, graph, impact_client, facility)
            c.key_terdampak = [] if facility else sorted(set(c.key_terdampak) | set(c.dampak["keys"]))
        state.catatan.append(c)
        result.new_notes.append(c)

    if result.new_documents:
        state.dokumen_baru_terakhir = timestamp
    if result.failed_enrichments:
        result.warnings.append(f"pengayaan (halaman/teks JDIH) gagal untuk {result.failed_enrichments} dokumen baru")
    if result.llm_failed:
        result.warnings.append(
            f"pendapat LLM gagal/tidak valid untuk {result.llm_failed} dari {result.llm_called} dokumen; "
            "dokumen itu hanya dinilai aturan"
        )
    if fetch and watchlist_check:
        pages = check_watchlist(state, wl, fetch, timestamp, result)
        run_canaries(state, pages, result)
    if fetch and bpk_check:
        check_bpk(state, wl, fetch, timestamp, result)
    if stale_check:
        result.warnings += check_stale(state, wl, timestamp)

    state.run_terakhir = timestamp
    result.set_code()
    return result


def weekly_due(last: str | None, now: str, days: int = 7) -> bool:
    elapsed = _days_since(last, now)
    return elapsed is None or elapsed >= days


def text_report(result: MonitorResult) -> str:
    failure_text = f"PEMANTAU GAGAL: {result.errors}\n(Bukan berarti tidak ada perubahan regulasi.)"
    if result.exit_code == CODE_FAILED and not (result.new_documents or result.watchlist_checked):
        return failure_text
    lines = [failure_text, ""] if result.errors else []
    lines += [
        f"Dokumen baru: {len(result.new_documents)}"
        + (f" (artikel dibuang: {result.dropped_articles})" if result.dropped_articles else "")
        + (" [putaran pertama: semua item feed dianggap baru]" if result.first_run else ""),
        f"Perlu ditinjau: {len(result.new_notes)}"
        + (" | watchlist diperiksa" if result.watchlist_checked else "")
        + (" | sitemap BPK diperiksa" if result.bpk_checked else "")
        + (" | kanari diperiksa" if result.canary_checked else ""),
    ]
    for c in result.new_notes:
        lines.append("")
        lines.append(f"[{c.kategori.upper()}] {c.identitas} ({c.tanggal_feed or c.sumber})")
        if c.perihal:
            lines.append(f"  {c.perihal}")
        lines.append(f"  {c.id_dokumen}")
        for a in c.alasan:
            lines.append(f"  - {a}")
        if c.key_terdampak:
            lines.append(f"  key data terdampak: {', '.join(c.key_terdampak)}")
        lines += [f"  {x}" for x in impact_lines(c)]
        if c.pemicu:
            lines.append(f"  periksa juga: {', '.join(c.pemicu)}")
        if c.mulai_berlaku_teks or c.diundangkan:
            lines.append(
                f"  dari teks: ditetapkan {c.ditetapkan or '?'}, diundangkan {c.diundangkan or '?'}, "
                f"mulai berlaku {c.mulai_berlaku_teks or '?'}"
                + (f", berlaku untuk {', '.join(c.berlaku_untuk)}" if c.berlaku_untuk else "")
            )
        for x in c.dicabut_teks:
            lines.append(f"  mencabut{' SEBAGIAN (' + x['bagian'] + ')' if x['sebagian'] else ''}: {x['identitas']}")
        for s in c.selisih:
            lines.append(f"  ! {s}")
        for g in c.galat_pengayaan:
            lines.append(f"  ? {g}")
    if result.llm_called:
        lines.append("")
        lines.append(
            f"LLM + teks: {result.llm_called} dokumen dinilai, {result.llm_promoted} masuk review hanya karena LLM"
            + (f", {result.llm_failed} gagal" if result.llm_failed else "")
        )
    if result.warnings:
        lines.append("")
        lines.append("PERINGATAN:")
        lines += [f"  ! {p}" for p in result.warnings]
    return "\n".join(lines)


def impact_lines(c: ImpactNote) -> list[str]:
    lines = []
    if c.pendapat_llm:
        llm = c.pendapat_llm
        lines.append(f"pendapat LLM + teks: {llm['kategori']}" + ("" if llm.get("valid", True) else " (tidak valid)")
                     + (f" ({llm['alasan']})" if llm.get("alasan") else ""))
    if c.dampak:
        d = c.dampak
        if d.get("sumber") == "gerbang_fasilitas":
            lines.append("dampak: fasilitas, tidak diberi key tarif (gerbang)")
        else:
            lines.append(
                f"dampak ({d.get('sumber')}): {', '.join(d.get('keys') or []) or 'tidak ada key teridentifikasi'}"
                + (f" | turunan: {', '.join(d['turunan'])}" if d.get("turunan") else "")
                + (f" | {len(d['fungsi'])} fungsi hitung" if d.get("fungsi") else "")
                + (f" | test: {', '.join(d['test'])}" if d.get("test") else "")
            )
    return lines
