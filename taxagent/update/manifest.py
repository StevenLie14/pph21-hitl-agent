from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from pathlib import Path

import yaml

from ..taxes import get as tax_module

DATA_DIR = tax_module().data_dir

SKILL_DIR = DATA_DIR / "skill"
EFFECTIVE_MODES = ("tahun_pajak", "tanggal")
FIELD_KINDS = ("rupiah", "persen", "orang")
CONSISTENCY_KINDS = ("kelipatan", "lapisan_naik")


@dataclass(frozen=True)
class Field:
    name: str
    kind: str
    range: tuple[Decimal, Decimal]
    meaning: str = ""
    llm: bool = True


@dataclass(frozen=True)
class Group:
    key: str
    terms: tuple[str, ...]
    field: tuple[Field, ...]
    layered: bool = False
    consistency: tuple[dict, ...] = ()

    def path(self, f: Field, index: str = "[i]") -> str:
        name = f.name.replace("[i]", index)
        return f"{self.key}{'' if name.startswith('[') else '.'}{name}"

    def catalog(self) -> str:
        return "\n".join(f"{self.path(f)}: {f.meaning}" for f in self.field if f.llm)

    def field_pattern(self) -> re.Pattern:
        alt = [re.escape(self.path(f)).replace(re.escape("[i]"), r"\[\d{1,2}\]") for f in self.field if f.llm]
        return re.compile(r"^(?:" + "|".join(alt) + ")$")


@dataclass(frozen=True)
class Manifest:
    skill: str
    name: str
    effective_mode: str
    data_file: str
    ratios: tuple[Decimal, Decimal]
    opening_prompt: str
    logic: tuple[str, ...]
    out_of_scope: dict
    groups: dict[str, Group] = field(default_factory=dict)

    @property
    def number_scope(self) -> tuple[str, ...]:
        return tuple(self.groups)

    def range_for(self, path: str) -> tuple[Decimal, Decimal] | None:
        plain = re.sub(r"\[\d+\]", "[]", path)
        for g in self.groups.values():
            for f in g.field:
                if g.path(f, "[]") == plain:
                    return f.range
        return None


def _decimal(x) -> Decimal:
    return Decimal(str(x))


def from_dict(data: dict) -> Manifest:
    if data.get("mode_berlaku") not in EFFECTIVE_MODES:
        raise ValueError(f"mode_berlaku harus salah satu dari {EFFECTIVE_MODES}")
    groups = {}
    for key, g in (data.get("kelompok") or {}).items():
        fields = []
        for name, spec in (g.get("field") or {}).items():
            if spec.get("jenis") not in FIELD_KINDS:
                raise ValueError(f"{key}.{name}: jenis harus salah satu dari {FIELD_KINDS}")
            r = spec.get("rentang")
            if not (isinstance(r, list) and len(r) == 2 and r[0] <= r[1]):
                raise ValueError(f"{key}.{name}: rentang [min, max] wajib")
            llm = spec.get("llm", True)
            if llm and not spec.get("arti"):
                raise ValueError(f"{key}.{name}: arti wajib untuk field yang ditanyakan ke LLM")
            fields.append(Field(str(name), spec["jenis"], (_decimal(r[0]), _decimal(r[1])), spec.get("arti", ""), llm))
        consistency = tuple(g.get("konsistensi") or ())
        for c in consistency:
            if c.get("jenis") not in CONSISTENCY_KINDS:
                raise ValueError(f"{key}: konsistensi {c} tidak dikenal (hanya {CONSISTENCY_KINDS})")
        if not g.get("istilah"):
            raise ValueError(f"{key}: istilah wajib (untuk memilih cuplikan teks)")
        groups[key] = Group(key, tuple(g["istilah"]), tuple(fields), bool(g.get("berlapis")), consistency)
    r = data.get("rasio") or [0.5, 3]
    return Manifest(data["skill"], data.get("nama", data["skill"]), data["mode_berlaku"], data["berkas_data"],
                    (_decimal(r[0]), _decimal(r[1])), " ".join(str(data["prompt_pembuka"]).split()),
                    tuple(data.get("logika") or ()), dict(data.get("di_luar_cakupan") or {}), groups)


@cache
def load(skill: str = "pph21") -> Manifest:
    return from_dict(yaml.safe_load((SKILL_DIR / f"{skill}.yaml").read_text(encoding="utf-8")))


def manifest_file(skill: str) -> Path:
    return SKILL_DIR / f"{skill}.yaml"
