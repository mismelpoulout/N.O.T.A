from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict

@dataclass
class CleanDoc:
    title: str
    url: str
    text: str

@dataclass
class Block:
    title: str
    bullets: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)     # aclaraciones cortas
    extra: Dict[str, List[str]] = field(default_factory=dict)  # p.ej. {"dosis": [...]}

@dataclass
class ExtractionResult:
    definicion: Block | None = None
    sintomas: Block | None = None
    diagnostico: Dict[str, Block] = field(default_factory=dict) # {"clinico":..., "laboratorio":..., "imagen":..., "diferencial":...}
    tratamiento: Dict[str, Block] = field(default_factory=dict) # {"conservador":..., "medicamentos":..., "quirurgico":...}
    conducta: Block | None = None
    citations: List[str] = field(default_factory=list)