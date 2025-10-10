# backend/core/pipeline.py
from __future__ import annotations

import re
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Tuple

import tldextract

from backend.core.db.local_search import LocalMedicalSearcher
from backend.core.cleaners import fetch_and_clean
# Si tienes un cliente unificado, lo inyectas desde app.py:
# from backend.core.search_client import SearchClient


# -------------------- Config y patrones --------------------

SPANISH_SECTIONS = {
    "definicion": (
        "definición", "definicion", "es una", "se define", "consiste en",
        "enfermedad", "entidad clínica", "cuadro clínico", "etiología", "causa"
    ),
    "sintomas": (
        "síntoma", "sintomas", "signos", "manifestaciones", "cuadro", "clínico",
        "fiebre", "tos", "odinofagia", "cefalea", "mialgia", "disnea", "rinorrea"
    ),
    "diagnostico": (
        "diagnóstico", "diagnosticar", "criterio", "criterios", "diferencial",
        "prueba", "test", "examen", "laboratorio", "radiografía", "pcr", "antígeno"
    ),
    "tratamiento": (
        "tratamiento", "manejo", "terapia", "antibiótico", "antiviral", "analgésico",
        "antiinflamatorio", "hidratación", "reposo", "antitérmico"
    ),
    "conducta": (
        "conducta", "plan", "seguimiento", "derivación", "derivar", "hospitalización",
        "criterios de ingreso", "criterios de hospitalización", "control a las 48 horas",
        "revaluación", "alta", "manejo ambulatorio", "educación", "alerta", "banderas rojas"
    ),
}

DOSIS_RX = re.compile(
    r"(?P<drug>[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\- ]{2,})"
    r".{0,30}?(?P<dose>\d{1,4}\s?(?:mg|mcg|g|ml))"
    r"(?:\s*(?:cada|c\/)\s*(?P<int>\d{1,2})\s*(?:h|horas))?",
    flags=re.IGNORECASE,
)

WHITELIST_WEIGHT = {
    # +3 confiables, +2 buenos, +1 neutros
    "who.int": 3, "cdc.gov": 3, "nejm.org": 3, "thelancet.com": 3,
    "mayoclinic.org": 2, "nih.gov": 3, "medlineplus.gov": 3,
    "merckmanuals.com": 2, "msdmanuals.com": 2,
    "gov": 2, "edu": 2,  # TLD
}

# -------------------- Helpers de texto / scoring --------------------

def _domain_weight(url: str) -> int:
    try:
        ext = tldextract.extract(url)
    except Exception:
        return 0
    dom = f"{ext.domain}.{ext.suffix}".lower()
    w = 0
    for k, v in WHITELIST_WEIGHT.items():
        # TLD puros (gov/edu)
        if k == ext.suffix:
            w = max(w, v)
        # dominio incluido
        if k in dom:
            w = max(w, v)
    return w

def _tokenize(s: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñ0-9]+", s.lower())

def _tf(sent: str, q_terms: set[str]) -> float:
    toks = _tokenize(sent)
    c = Counter(toks)
    return sum(c[t] for t in q_terms) / (1 + len(toks))

def _cos(a: Counter, b: Counter) -> float:
    inter = set(a) & set(b)
    num = sum(a[t]*b[t] for t in inter)
    na = math.sqrt(sum(v*v for v in a.values()))
    nb = math.sqrt(sum(v*v for v in b.values()))
    return 0.0 if na == 0 or nb == 0 else num/(na*nb)

def _to_vec(text: str) -> Counter:
    return Counter(_tokenize(text))

def _mmr_select(candidates: list[str], q: str, k: int = 24, lam: float = 0.75) -> list[str]:
    """Selección MMR simple (diversidad) sobre bolsa de palabras."""
    qv = _to_vec(q)
    cand_vecs = [_to_vec(c) for c in candidates]
    selected: list[str] = []
    used_idx: set[int] = set()
    while len(selected) < min(k, len(candidates)):
        best_i, best_score = None, -1e9
        for i, vec in enumerate(cand_vecs):
            if i in used_idx:
                continue
            rel = _cos(vec, qv)
            div = max((_cos(vec, _to_vec(s)) for s in selected), default=0.0)
            score = lam*rel - (1-lam)*div
            if score > best_score:
                best_score, best_i = score, i
        used_idx.add(best_i)  # type: ignore[arg-type]
        selected.append(candidates[best_i])  # type: ignore[index]
    return selected

def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    sents = re.split(r"(?<=[\.\!\?])\s+(?=[A-ZÁÉÍÓÚÜÑ])", text)
    return [s.strip() for s in sents if 40 <= len(s.strip()) <= 300]

def _classify(sent: str) -> str|None:
    s = sent.lower()
    for key, kws in SPANISH_SECTIONS.items():
        if any(kw in s for kw in kws):
            return key
    return None

def _extract_doses(texts: list[str]) -> list[str]:
    found: list[str] = []
    for t in texts:
        for m in DOSIS_RX.finditer(t):
            drug = re.sub(r"\s{2,}", " ", m.group("drug")).strip(" .,:;")
            dose = m.group("dose")
            every = m.group("int")
            piece = f"- {drug}: {dose}"
            if every:
                piece += f" cada {every} h"
            # evita duplicados case-insensitive
            if piece.lower() not in (x.lower() for x in found):
                found.append(piece)
    return found[:8]

# -------------------- Resumen estructurado --------------------

def build_structured_markdown(query: str, cleaned_docs: list[dict]) -> tuple[str, list[str]]:
    """
    Recibe documentos LIMPIOS: [{title,url,text}, ...]
    Devuelve (markdown, citas_urls) con estructura clínica en castellano.
    """
    docs = [d for d in cleaned_docs if d.get("text")]
    if not docs:
        return f"**Pregunta:** {query}\n\n_No hay contenido suficiente para resumir._", []

    q_terms = {t for t in _tokenize(query) if len(t) >= 3}

    # 1) Peso por confianza de dominio
    doc_weights: list[tuple[float, dict]] = []
    for d in docs:
        w = float(_domain_weight(d.get("url", "")))
        doc_weights.append((w, d))
    doc_weights.sort(key=lambda x: x[0], reverse=True)

    # 2) Universo de frases con score de relevancia
    candidate_sents: list[tuple[float, str]] = []
    for w, d in doc_weights:
        sents = _split_sentences(d["text"])
        for s in sents:
            rel = _tf(s, q_terms)
            score = rel + 0.15 * w
            if score > 0:
                candidate_sents.append((score, s))

    if not candidate_sents:
        backup = []
        for _, d in doc_weights:
            backup.extend(_split_sentences(d["text"])[:8])
        backup = [b for b in backup if 40 <= len(b) <= 300]
        picked = _mmr_select(backup, query, k=24, lam=0.75)
    else:
        candidate_sents.sort(key=lambda x: (-x[0], len(x[1])))
        top = [s for _, s in candidate_sents[:220]]
        picked = _mmr_select(top, query, k=24, lam=0.75)

    # 3) Clasificar por secciones
    buckets = defaultdict(list)
    for s in picked:
        tag = _classify(s) or "otros"
        buckets[tag].append("• " + s)

    # 4) Dosis
    doses = _extract_doses(picked)

    # 5) Puntos clave
    key_points = ["– " + s for s in picked[:6]]

    # 6) Referencias (únicas, priorizando confiables)
    citations: list[str] = []
    seen_c = set()
    for _, d in doc_weights:
        u = d.get("url")
        if u and u not in seen_c:
            seen_c.add(u)
            citations.append(u)
        if len(citations) >= 8:
            break

    # 7) Fallbacks para secciones vacías
    def _fallback(tag: str, alt_from: list[str]) -> list[str]:
        if buckets.get(tag):
            return buckets[tag]
        for s in alt_from:
            if len(s) > 60:
                return ["• " + s]
        return []

    alt = picked
    defin = _fallback("definicion", alt)
    sx    = _fallback("sintomas",   alt)
    dx    = _fallback("diagnostico",alt)
    tx    = _fallback("tratamiento",alt)
    cx    = _fallback("conducta",   alt)

    # 8) Render Markdown
    sec: list[str] = []
    sec.append(f"**Pregunta:** {query}\n")

    sec.append("## Puntos clave")
    sec.append("\n".join(key_points) if key_points else "– Sin hallazgos clave.")

    if defin:
        sec.append("\n## Definición")
        sec.append("\n".join(defin[:6]))

    if sx:
        sec.append("\n## Síntomas")
        sec.append("\n".join(sx[:10]))

    if dx:
        sec.append("\n## Diagnóstico")
        sec.append("\n".join(dx[:10]))

    if tx:
        sec.append("\n## Tratamiento")
        sec.append("\n".join(tx[:12]))

    if doses:
        sec.append("\n**Dosis (orientativas; confirmar con guía local):**")
        sec.append("\n".join(doses))

    if cx:
        sec.append("\n## Conducta / Seguimiento")
        sec.append("\n".join(cx[:10]))

    sec.append("\n## Referencias principales")
    if citations:
        sec.append("\n".join(f"{i+1}. {u}" for i, u in enumerate(citations, 1)))
    else:
        sec.append("– (sin referencias)")

    md = "\n".join(sec).strip()
    return md, citations

# -------------------- Pipeline --------------------

class NOTAPipeline:
    """
    1) Busca local.
    2) Si no alcanza, busca web con search_client (inyectado).
    3) Limpia, fusiona, estructura y devuelve Markdown + citas.
    """
    def __init__(self, db_dir: str = "./data", search_client=None):
        self.searcher = LocalMedicalSearcher(db_dir)
        self.search = search_client
        self.output_db = f"{db_dir}/output.db"

    async def run(self, q: str) -> Tuple[dict, str]:
        q = q.strip()
        notes = {"query_norm": q, "citations": [], "local_added": 0, "web_added": 0}

        if not q:
            return notes, "⚠️ Pregunta vacía."

        # 1) LOCAL
        local = await self.searcher.search(q, top_k=8)
        if local:
            local_texts = [{"title": r.get("title",""), "url": r.get("url",""), "text": r["content"]} for r in local]
            md, cits = build_structured_markdown(q, local_texts)
            notes["citations"] = cits
            return notes, md

        # 2) WEB (si hay search_client)
        cleaned: list[dict] = []
        if self.search:
            try:
                hits = await self.search.search(q, count=8)
            except Exception:
                hits = []
            for it in hits:
                url = it.get("url");  name = it.get("name","")
                if not url:
                    continue
                try:
                    txt = await fetch_and_clean(url)
                except Exception:
                    txt = ""
                if not txt:
                    continue
                cleaned.append({"title": name, "url": url, "text": txt})
            notes["web_added"] = len(cleaned)

        if cleaned:
            md, cits = build_structured_markdown(q, cleaned)
            notes["citations"] = cits
            return notes, md

        # 3) Sin resultados
        return notes, f"**Pregunta:** {q}\n\nNo encontré información suficiente en la base ni en la web."