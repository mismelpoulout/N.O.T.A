# -*- coding: utf-8 -*-
"""
Módulo: ClinicalClassifier
Detecta el contexto clínico principal de la pregunta o texto.
Clasifica en categorías SNOMED-like (médica, quirúrgica, infecciosa, metabólica, oncológica, obstétrica, pediátrica...).
"""
from __future__ import annotations
import re
from typing import Dict

# patrones por área principal
CLINICAL_AREAS: Dict[str, list[str]] = {
    "médica": [
        "diabetes", "hipertensión", "asma", "epilepsia", "alzheimer",
        "artritis", "depresión", "insuficiencia", "anemia", "colitis"
    ],
    "quirúrgica": [
        "apendicitis", "hernia", "fractura", "colecistectom", "tumor",
        "biopsia", "resección", "laparoscop", "injerto", "cirugía"
    ],
    "infecciosa": [
        "virus", "bacteria", "parásito", "fungi", "infección",
        "covid", "influenza", "neumonía", "vih", "sepsis"
    ],
    "metabólica": [
        "diabetes", "obesidad", "tiroides", "hipotiroidismo", "hipertiroidismo",
        "lipidemia", "gotta", "osteoporosis"
    ],
    "oncológica": [
        "cáncer", "tumor", "neoplasia", "carcinoma", "leucemia", "melanoma"
    ],
    "obstétrica": [
        "embarazo", "gestante", "parto", "cesárea", "preeclampsia", "lactancia"
    ],
    "pediátrica": [
        "niño", "niña", "lactante", "adolescente", "infantil", "recién nacido"
    ]
}

def classify_context(text: str) -> str:
    t = text.lower()
    for area, kws in CLINICAL_AREAS.items():
        if any(k in t for k in kws):
            return area
    return "general"

def allowed_sections(area: str) -> list[str]:
    """Define qué secciones clínicas deben mostrarse según especialidad."""
    if area in ("médica", "metabólica", "infecciosa", "pediátrica"):
        return ["definicion", "sintomas", "diagnostico", "tratamiento", "conducta"]
    if area == "quirúrgica":
        return ["definicion", "sintomas", "diagnostico", "tratamiento_quirurgico", "conducta"]
    if area == "obstétrica":
        return ["definicion", "sintomas", "diagnostico", "tratamiento", "conducta"]
    if area == "oncológica":
        return ["definicion", "sintomas", "diagnostico", "tratamiento", "pronóstico"]
    return ["definicion", "sintomas", "diagnostico", "tratamiento", "conducta"]