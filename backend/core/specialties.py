# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Set

SPECIALTY_KEYWORDS: Dict[str, set[str]] = {
    "pediatria": {
        "pediatr", "niño", "niña", "lactante", "adolescente",
        "menor de", "peso al nacer", "apgar", "edad gestacional",
        "mg/kg", "ml/kg"
    },
    "obstetricia": {
        "obstetr", "gestante", "embarazo", "puerperio", "parto",
        "feto", "placenta", "g", "semanas de gestación", "sg"
    },
    "infectologia": {
        "antibiótico", "antiviral", "cultivo", "pcr", "antígeno",
        "resistencia", "aislamiento", "profilaxis", "zoonosis"
    },
    "neumologia": {"espirometría", "oximetría", "tos", "disnea", "rx", "infiltrado"},
    "cardiologia": {"ecg", "troponina", "insuficiencia cardiaca", "hta", "acv", "trombo"},
    # agrega más si lo necesitas…
}

def detect_specialties(text: str) -> Set[str]:
    s = text.lower()
    hits: Set[str] = set()
    for sp, kws in SPECIALTY_KEYWORDS.items():
        if any(kw in s for kw in kws):
            hits.add(sp)
    return hits

def score_specialty(sent: str, expected: Set[str]) -> float:
    """Score extra si la frase coincide con la especialidad del contexto."""
    if not expected:
        return 0.0
    s = sent.lower()
    sc = 0.0
    for sp in expected:
        kws = SPECIALTY_KEYWORDS.get(sp, set())
        if any(kw in s for kw in kws):
            sc += 1.0
    return min(sc, 2.0)  # cap