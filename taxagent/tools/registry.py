from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable

from ..settings import get_settings
from ..taxes import ToolSpec
from ..taxes import get as tax_module
from . import schemas as S

log = logging.getLogger(__name__)

DISCLAIMER = (
    "Hasil ini merupakan alat bantu hitung, bukan nasihat pajak resmi. "
    "Untuk pelaporan, konfirmasikan kepada konsultan pajak atau DJP."
)


def error_result(message: str, hint: str = "") -> dict:
    return {"berhasil": False, "galat": message, "saran": hint}


def graph_enabled() -> bool:
    if not get_settings().graph_tools:
        return False
    from ..environment import load_neo4j_env

    load_neo4j_env()
    return bool(get_settings().neo4j_v2_uri)


def period_end(result: dict, kw: dict) -> dt.date:
    year = int(result.get("tahun_pajak") or kw.get("tahun_pajak") or dt.date.today().year)
    month = result.get("masa_pajak") or kw.get("masa_pajak")
    try:
        month = int(month)
    except (TypeError, ValueError):
        month = 12
    if not 1 <= month <= 12:
        month = 12
    end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)
    return min(dt.date.today(), end - dt.timedelta(days=1))


def result_basis_status(result: dict, kw: dict) -> list[dict] | None:
    if not result.get("dasar_hukum") or not graph_enabled() or get_settings().graph_ablation:
        return None
    try:
        from .regulation_graph import basis_status

        return basis_status(list(result["dasar_hukum"]), period_end(result, kw))
    except Exception:  # noqa: BLE001
        log.warning("legal-basis status from the graph failed", exc_info=True)
        return None


def result_locations(references) -> list[dict] | None:
    if not references or not graph_enabled() or get_settings().graph_ablation:
        return None
    try:
        from .regulation_graph import reference_locations

        return reference_locations(list(references)) or None
    except Exception:  # noqa: BLE001
        log.warning("reference locations from the graph failed", exc_info=True)
        return None


def report_possibly_stale(**kw) -> dict:
    from ..agent import stale_reports

    graph_lookup = None
    if graph_enabled():
        from .regulation_graph import find_regulation

        graph_lookup = find_regulation
    return stale_reports.report(kw.get("reason", ""), kw.get("details", ""), peraturan=kw.get("regulation", ""),
                                  tanggal_fakta=kw.get("fact_date", ""), graf=graph_lookup)


GENERIC_SPECS: list[ToolSpec] = [
    (
        report_possibly_stale,
        S.UsangArgs,
        "Catat permintaan pemeriksaan bila data kalkulator atau graf mungkin USANG: tahun pajak belum punya tabel "
        "tarif, pengguna menyebut peraturan yang tidak ada di graf, atau peraturan dasar data kalkulator sudah "
        "dicabut. Tool ini TIDAK mengubah data dan tidak memberi angka; klaimmu dicek dulu dan ditolak bila "
        "keliru. Setelah memanggilnya tetap jawab dengan data yang ada dan katakan bahwa data mungkin belum "
        "mencakup aturan terbaru.",
    ),
]


def _graph_specs() -> list[ToolSpec]:
    if get_settings().graph_ablation:
        from .graph_ablation import SPECS

        return list(SPECS)
    from . import regulation_graph as G

    return [
        (G.find_regulation, S.PeraturanArgs,
         "Cari sebuah peraturan di graf peraturan dan statusnya PADA tanggal tertentu (belum berlaku, berlaku, diubah, "
         "berlaku sebagian, dicabut, berakhir) beserta pencabut dan tanggalnya. Untuk pertanyaan status atau dasar "
         "hukum, BUKAN untuk menghitung pajak."),
        (G.amendment_chain, S.PeraturanArgs,
         "Riwayat perubahan sebuah peraturan, kronologis: siapa yang mencabut/mengubahnya dan apa yang dicabut/diubahnya, "
         "dengan tanggal efektif, kelas bukti, kutipan pasal, dan pasal_terdampak (daftar pasal yang diubah, disisipkan, "
         "atau dicabut). Untuk pertanyaan 'pasal apa saja yang diubah peraturan X', panggil dengan peraturan pengubah X."),
        (G.get_article, S.PasalArgs,
         "Ambil bunyi satu pasal sebuah peraturan beserta halaman PDF, status peraturan pada tanggal itu, dan peringatan "
         "bila pasal itu sudah dicabut. Untuk mengutip bunyi pasal sebagai dasar hukum."),
        (G.search_text, S.CariTeksArgs,
         "Cari pasal peraturan yang relevan dengan pertanyaan (pencarian semantik; boleh kalimat biasa, tidak harus kata "
         "yang persis ada di teks). Default hanya peraturan dan pasal yang berlaku pada tanggal itu. Untuk pertanyaan "
         "'peraturan mana yang mengatur X'."),
        (G.regulation_legal_basis, S.PeraturanArgs,
         "Dasar hukum sebuah peraturan (konsiderans Menimbang/Mengingat: pasal yang mendelegasikan, UU/PP induk) dan "
         "peraturan pelaksana yang masih berlaku dari peraturan itu, dengan status pada tanggal itu. Untuk pertanyaan "
         "'peraturan ini turunan dari mana' atau 'aturan pelaksana UU/PP ini apa saja'."),
        (G.search_faq, S.FaqArgs,
         "Cari FAQ DJP (tanya-jawab resmi pajak.go.id) untuk pertanyaan praktis: tata cara, aplikasi, contoh kasus. "
         "Hasilnya PENJELASAN, bukan dasar hukum: jangan dipakai untuk angka hitungan; peraturan yang disebut FAQ "
         "harus dicek dengan find_regulation atau get_article sebelum dikutip."),
        (G.skill_value, S.SkillArgs,
         "Nilai data yang dipakai kalkulator untuk sebuah key (mis. PTKP, biaya jabatan) pada tahun pajak tanggal itu, "
         "dasar hukumnya, dan status peraturan pendefinisinya. Untuk pertanyaan 'berapa PTKP sekarang dan dasarnya apa'."),
    ]


def base_specs() -> list[ToolSpec]:
    return [*tax_module().tool_specs(), *GENERIC_SPECS]


def all_specs(with_graph: bool | None = None) -> list[ToolSpec]:
    with_graph = graph_enabled() if with_graph is None else with_graph
    return base_specs() + (_graph_specs() if with_graph else [])


def langchain_tools():
    from langchain_core.tools import StructuredTool

    return [StructuredTool.from_function(func=fn, name=fn.__name__, description=description, args_schema=args)
            for fn, args, description in all_specs()]


def all_tool_names() -> list[str]:
    return [fn.__name__ for fn, _, _ in all_specs(with_graph=True)]


def graph_tool_names() -> set[str]:
    return {fn.__name__ for fn, _, _ in _graph_specs()}


def find_tool(name: str) -> tuple[Callable[..., dict], type] | None:
    for fn, schema, _ in all_specs(with_graph=True):
        if fn.__name__ == name:
            return fn, schema
    return None


def call_tool(name: str, **kw) -> dict:
    found = find_tool(name)
    if found is None:
        raise KeyError(f"tool '{name}' tidak ada; pilihan: {all_tool_names()}")
    fn, schema = found
    unknown = sorted(set(kw) - set(schema.model_fields))
    if unknown:
        return error_result(f"argumen tidak dikenal untuk {name}: {', '.join(unknown)}",
                     f"Argumen yang sah: {', '.join(schema.model_fields)}.")
    return fn(**kw)
