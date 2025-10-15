# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import List, Dict

# patrones
RGX_PERKG = re.compile(
    r"(?P<drug>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][\w \-]{2,})\s*[:\-]?\s*"
    r"(?P<dose>\d+(?:\.\d+)?)\s*(?P<unit>mg|mcg|g)\s*/\s*kg"
    r"(?:\s*/\s*(?P<freq>\d+)\s*(?:h|horas))?",
    re.IGNORECASE
)

RGX_FIXED = re.compile(
    r"(?P<drug>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][\w \-]{2,})\s*[:\-]?\s*"
    r"(?P<dose>\d{1,4})\s*(?P<unit>mg|mcg|g|ml)"
    r"(?:\s*/\s*(?P<freq>\d+)\s*(?:h|horas))?",
    re.IGNORECASE
)

RGX_AGE = re.compile(
    r"(?:edad|niñ[oa]|lactante|adult[oa]|ancian[oa]|geriatri\w+|"
    r"\d{1,2}\s*(?:mes(?:es)?|años?))", re.IGNORECASE
)

def extract_dose_table(texts: List[str]) -> List[Dict]:
    """
    Devuelve filas: {drug, schema (perkg/fixed), dose, unit, freq_h, note}
    """
    rows: List[Dict] = []
    def push(drug, schema, dose, unit, freq, note=""):
        if not drug or not dose: return
        rows.append({
            "drug": re.sub(r"\s{2,}", " ", drug).strip(" .,:;"),
            "schema": schema,
            "dose": dose,
            "unit": unit.lower(),
            "freq_h": int(freq) if freq else None,
            "note": note.strip()
        })

    for t in texts:
        # captar contexto de edad/nota
        note = " ".join(RGX_AGE.findall(t))[:60]
        for m in RGX_PERKG.finditer(t):
            push(m.group("drug"), "perkg", m.group("dose"), m.group("unit"), m.group("freq"), note)
        for m in RGX_FIXED.finditer(t):
            push(m.group("drug"), "fixed", m.group("dose"), m.group("unit"), m.group("freq"), note)

    # compactar duplicados simples
    seen = set()
    uniq = []
    for r in rows:
        key = (r["drug"].lower(), r["schema"], r["dose"], r["unit"], r["freq_h"])
        if key in seen: continue
        seen.add(key)
        uniq.append(r)
    return uniq[:16]

def doses_to_markdown(rows: List[Dict]) -> str:
    if not rows: return ""
    # tabla Markdown simple
    head = "| Fármaco | Esquema | Dosis | Freq. | Nota |\n|---|---|---|---|---|"
    body = []
    for r in rows:
        schema = "mg/kg" if r["schema"] == "perkg" else "fija"
        dose = f"{r['dose']} {r['unit']}"
        freq = f"cada {r['freq_h']} h" if r["freq_h"] else "—"
        note = r["note"] or "—"
        body.append(f"| {r['drug']} | {schema} | {dose} | {freq} | {note} |")
    return "\n".join([head] + body)