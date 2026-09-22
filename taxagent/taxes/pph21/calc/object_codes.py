from __future__ import annotations

from functools import lru_cache

import yaml

from .models import PPh21Result
from .rates import DATA_DIR

_FIXED = {
    "pegawai_tetap": "21-100-01",
    "pensiunan": "21-100-02",
    "dewan_komisaris": "21-100-10",
    "pasal17_langsung_mantan_pegawai": "21-100-11",
    "pasal17_langsung_peserta_pensiun_pegawai": "21-100-12",
    "tahun_ketiga": "21-100-25",
    "final_pesangon": "21-401-01",
    "final_manfaat_pensiun": "21-401-02",
    "pph26": "27-100-99",
}
_NON_PERMANENT = {False: ("21-100-35", "21-100-24", "21-100-30"), True: ("21-100-27", "21-100-29", "21-100-31")}


@lru_cache(maxsize=1)
def load_object_codes() -> dict:
    return yaml.safe_load((DATA_DIR / "kode_objek_pajak.yaml").read_text(encoding="utf-8"))


def _choose(mapping: dict, value: str, name: str) -> str:
    key = (value or "").strip().lower()
    if not key:
        return ""
    if key not in mapping:
        raise ValueError(f"{name} '{value}' tidak dikenali; pilih " + ", ".join(mapping))
    return mapping[key]


def determine_object_code(h: PPh21Result, jenis_jasa: str = "", jenis_kegiatan: str = "", golongan: str = "",
                          ikn: bool = False) -> str:
    data = load_object_codes()
    j = h.jenis_perhitungan
    if j.startswith("pegawai_tetap"):
        return "21-100-32" if ikn else "21-100-01"
    if j.startswith("pegawai_tidak_tetap"):
        monthly, daily_up_to_limit, daily_above_limit = _NON_PERMANENT[ikn]
        if "bulanan" in j.split("_"):
            return monthly
        return daily_above_limit if h.metode_tarif.startswith("Tarif Pasal 17") else daily_up_to_limit
    if j == "bukan_pegawai":
        return _choose(data["jenis_jasa"], jenis_jasa, "jenis_jasa")
    if j == "pasal17_langsung_peserta_kegiatan":
        return _choose(data["jenis_kegiatan"], jenis_kegiatan, "jenis_kegiatan")
    if j == "final_honorarium_pns":
        return data["honorarium_golongan"].get((golongan or "").strip().upper(), "")
    for prefix, code in _FIXED.items():
        if j.startswith(prefix):
            return code
    return ""


def object_code_info(kode: str) -> dict | None:
    if not kode:
        return None
    data = load_object_codes()
    return {"kode": kode, **data["kode"][kode], "sumber": data["sumber"]}
