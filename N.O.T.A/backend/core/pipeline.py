# backend/core/pipeline.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import re, random
from collections import Counter, defaultdict
from typing import Tuple, Dict, List, Optional

from backend.core.db.local_search import LocalMedicalSearcher
from backend.core.db.ios_fts_search import IOSFTSSearcher
from backend.core.cached_fetch import cached_fetch_and_clean
from backend.core.dose_parser import extract_dose_table, doses_to_markdown
from backend.core.evidence import evidence_score
from backend.core.specialties import detect_specialties, score_specialty

# ---------- Secciones
SPANISH_SECTIONS: dict[str, tuple[str, ...]] = {
    "definicion": ("definición","definicion","es una","se define","consiste","etiología","epidemiología","prevalencia","incidencia","clasificación","factores de riesgo"),
    "sintomas": ("síntoma","sintomas","signos","manifestaciones","cuadro clínico","dolor","tos","fiebre","disnea","cefalea","astenia","náuseas","vómitos"),
    "diagnostico": ("diagnóstico","criterios","diferencial","laboratorio","imagen","ecografía","radiografía","tac","rm","pcr","antígeno","biopsia","prueba"),
    "tratamiento": ("tratamiento","manejo","terapia","farmacológico","medicamentos","rehabilitación","no farmacológico","antibiótico","analgésico","antiinflamatorio","insulina","metformina","antihipertensivo","quirúrgico","cirugía","operación","resección","injerto"),
    "conducta": ("conducta","seguimiento","derivación","control","educación","alta","criterios de ingreso","banderas rojas","reevaluación","hospitalización"),
}

# ---------- Utilidades NLP
def _tokenize(s: str) -> list[str]:
    return re.findall(r"[a-záéíóúüñ0-9]+", (s or "").lower())

def _to_vec(text: str) -> Counter: return Counter(_tokenize(text))

def _cos(a: Counter, b: Counter) -> float:
    inter = set(a) & set(b); num = sum(a[t]*b[t] for t in inter)
    na = sum(v*v for v in a.values())**0.5; nb = sum(v*v for v in b.values())**0.5
    return 0.0 if na==0 or nb==0 else num/(na*nb)

def _mmr_select(cands: list[str], q: str, k: int = 40, lam: float = .75) -> list[str]:
    qv = _to_vec(q); vecs = [_to_vec(c) for c in cands]; sel, used = [], set()
    while len(sel) < min(k, len(cands)):
        best_i, best = None, -1e9
        for i, v in enumerate(vecs):
            if i in used: continue
            rel = _cos(v, qv)
            div = max((_cos(v, _to_vec(s)) for s in sel), default=0.0)
            score = lam*rel - (1-lam)*div
            if score > best: best, best_i = score, i
        if best_i is None: break
        used.add(best_i); sel.append(cands[best_i])
    return sel

def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "")
    out = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ])", text)
    return [s.strip() for s in out if 40 <= len(s) <= 400]

def _classify(sent: str) -> str | None:
    s = (sent or "").lower()
    for k, kws in SPANISH_SECTIONS.items():
        if any(kw in s for kw in kws): return k
    return None

def _normalize_sentence(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\s*\(.*?\)", "", s)
    s = s.replace("..",".").strip(". ")
    return (s[0].upper()+s[1:]) if s else s

def _summarize(sents: list[str], n: int) -> list[str]:
    seen, out = set(), []
    for s in sents:
        s = _normalize_sentence(s)
        if not s: continue
        key = re.sub(r"[^a-z0-9áéíóúüñ ]","", s.lower())
        if key in seen: continue
        seen.add(key)
        out.append("• " + (s if len(s) <= 220 else (s.split(". ")[0]+ ".")))
        if len(out) >= n: break
    return out

def _is_surgical_relevant(texts: list[str]) -> bool:
    blob = " ".join(texts).lower()
    return any(t in blob for t in ("cirug","quirúrg","operaci","resecc","injerto"))

# ---------- Cobertura mínima para “corte temprano”
REQUIRED_SECTIONS = ("definicion", "sintomas", "diagnostico", "tratamiento")
def _coverage_ok(buckets: dict[str, list[str]]) -> bool:
    return all(buckets.get(sec) for sec in REQUIRED_SECTIONS)

# ---------- Ranking por evidencia / dominio
PENALIZE_DOMAINS = ("wikipedia.org","youtube.com","youtu.be")
def _domain_bonus(url: str, preferred: list[str]) -> float:
    url = (url or "").lower()
    if any(bad in url for bad in PENALIZE_DOMAINS): return -0.5
    if any(p in url for p in preferred):            return +0.6
    return 0.0

# ---------- Render
def build_structured_markdown(query: str, cleaned_docs: list[dict], preferred_domains: list[str]) -> tuple[str, list[str]]:
    docs = [d for d in cleaned_docs if d.get("text")]
    if not docs:
        return f"**Pregunta:** {query}\n\n_No hay información suficiente._", []

    q_terms = {t for t in _tokenize(query) if len(t) >= 3}
    expected_specs = detect_specialties(query)

    weighted: list[tuple[float,str,dict]] = []
    for d in docs:
        url = d.get("url",""); title = d.get("title",""); text = d.get("text") or ""
        ev = evidence_score(text[:2000], url, title)
        bonus = _domain_bonus(url, preferred_domains)
        for s in _split_sentences(text):
            tf = sum(1 for t in q_terms if t in s.lower()) / (1 + len(s))
            sp = score_specialty(s, expected_specs)
            score = tf + 0.25*ev + 0.15*sp + bonus
            if score > 0:
                weighted.append((score, s, d))

    if not weighted:
        for d in docs:
            for s in _split_sentences(d.get("text",""))[:8]:
                weighted.append((0.1, s, d))

    weighted.sort(key=lambda x: -x[0])
    picked = _mmr_select([s for _,s,_ in weighted][:300], query, k=40)

    buckets: dict[str, list[str]] = defaultdict(list)
    for s in picked:
        buckets[_classify(s) or "otros"].append(s)

    dose_rows = extract_dose_table(picked)
    surgical_relevant = _is_surgical_relevant(picked)

    sec: list[str] = [f"**Pregunta:** {query}\n"]

    if buckets.get("definicion"):
        sec.append("## Definición y Epidemiología")
        sec += _summarize(buckets["definicion"], 6)

    if buckets.get("sintomas"):
        sec.append("\n## Síntomas")
        sec += _summarize(buckets["sintomas"], 10)

    if buckets.get("diagnostico"):
        sec.append("\n## Diagnóstico")
        sec.append("**Métodos clínicos y complementarios:**")
        sec += _summarize(buckets["diagnostico"], 10)

    if buckets.get("tratamiento"):
        sec.append("\n## Tratamiento")
        conserv = [s for s in buckets["tratamiento"] if any(x in s.lower() for x in ("rehab","repos","hidrat","no farmac","educac","ejerc"))]
        if conserv:
            sec.append("**Tratamiento conservador:**")
            sec += _summarize(conserv, 6)

        medic = [s for s in buckets["tratamiento"] if any(x in s.lower() for x in ("antib","analg","antiinflam","farmac","insulin","metformin","antihipert"))]
        if medic:
            sec.append("\n**Tratamiento medicamentoso:**")
            sec += _summarize(medic, 8)

        if dose_rows:
            sec.append("\n**Dosis (según guías; confirmar con contexto local):**")
            sec.append(doses_to_markdown(dose_rows))

        if surgical_relevant:
            surg = [s for s in buckets["tratamiento"] if "cirug" in s.lower() or "oper" in s.lower() or "resecc" in s.lower()]
            if surg:
                sec.append("\n**Tratamiento quirúrgico:**")
                sec += _summarize(surg, 4)

    if buckets.get("conducta"):
        sec.append("\n## Conducta y Seguimiento")
        sec += _summarize(buckets["conducta"], 8)

    suggestions = [
        f"Pronóstico y complicaciones de {query.lower()}",
        f"Diferencial de {query.lower()} por especialidad",
        f"Nuevas guías y terapias actualizadas para {query.lower()}",
        f"Prevención / profilaxis en {query.lower()}",
    ]
    random.shuffle(suggestions)
    sec.append("\n## Otras sugerencias")
    sec += [f"- {s}" for s in suggestions[:3]]

    # referencias ordenadas por evidencia + bonus dominio
    url_best: dict[str, float] = {}
    for _, _, d in weighted:
        u = d.get("url")
        if not u: continue
        ev = evidence_score((d.get("text") or "")[:2000], u, d.get("title",""))
        url_best[u] = max(url_best.get(u, -9e9), ev + _domain_bonus(u, preferred_domains))

    citations = [u for u,_ in sorted(url_best.items(), key=lambda x: -x[1])][:12]
    sec.append("\n## Referencias principales")
    sec += [f"{i+1}. {u}" for i,u in enumerate(citations,1)] if citations else ["– (sin referencias)"]

    return "\n".join(sec).strip(), citations

# ---------- Pipeline
class NOTAPipeline:
    """
    Orden de búsqueda:
      1) DB local (LocalMedicalSearcher)
      2) iOS FTS (medical_fts.sqlite)
      3) Sitios nacionales preferidos (site:dominio)
      4) Resto de la web (filtro por evidencia y penalizaciones)
    Se detiene temprano si la cobertura de secciones es suficiente.
    """
    def __init__(self, db_dir: str, search_client, ios_fts_db: Optional[str], output_db: Optional[str], preferred_domains: Optional[List[str]] = None):
        self.searcher = LocalMedicalSearcher(db_dir)
        self.ios_fts = IOSFTSSearcher(ios_fts_db) if ios_fts_db and len(ios_fts_db) else None
        self.search = search_client
        self.cache_db = f"{db_dir.rstrip('/')}/cache.db"
        self.preferred_domains = preferred_domains or []

    async def _render_if_complete(self, q: str, docs: List[dict]) -> Tuple[bool, Tuple[dict,str]]:
        md, cits = build_structured_markdown(q, docs, self.preferred_domains)
        # chequea cobertura
        # volvemos a clasificar rápido para ver cobertura
        buckets = defaultdict(list)
        for s in _mmr_select([ss for d in docs for ss in _split_sentences(d.get("text",""))][:300], q, k=40):
            buckets[_classify(s) or "otros"].append(s)
        if _coverage_ok(buckets):
            notes = {"citations": cits}
            return True, (notes, md)
        return False, ({}, md)

    async def run(self, q: str) -> Tuple[dict, str]:
        q = (q or "").strip()
        notes = {"query_norm": q, "citations": [], "local_added": 0, "ios_fts_added": 0, "web_added": 0, "cache_hits": 0}
        if not q:
            return notes, "⚠️ Pregunta vacía."

        # 1) Local DB
        docs: List[dict] = []
        local = await self.searcher.search(q, top_k=10)
        if local:
            docs.extend({"title": r.get("title",""), "url": r.get("url",""), "text": r.get("content","")} for r in local)
            notes["local_added"] = len(local)
            done, result = await self._render_if_complete(q, docs)
            if done:
                notes["citations"] = result[0]["citations"]; return notes, result[1]

        # 2) iOS FTS
        if self.ios_fts:
            ios_hits = self.ios_fts.search(q, top_k=10)
            if ios_hits:
                docs.extend({"title": r.get("title",""), "url": r.get("url",""), "text": r.get("content","")} for r in ios_hits)
                notes["ios_fts_added"] = len(ios_hits)
                done, result = await self._render_if_complete(q, docs)
                if done:
                    notes["citations"] = result[0]["citations"]; return notes, result[1]

        # 3) Sitios preferidos (MINSAL, Intramed, …)
        if self.search and self.preferred_domains:
            preferred_docs: List[dict] = []
            for dom in self.preferred_domains:
                try:
                    hits = await self.search.search(f"site:{dom} {q}", count=4)
                except Exception:
                    hits = []
                for it in hits:
                    url = it.get("url"); name = it.get("name","") or ""
                    if not url: continue
                    txt, from_cache = await cached_fetch_and_clean(url, db_path=self.cache_db, ttl_hours=24*7, return_flag=True)
                    if from_cache: notes["cache_hits"] += 1
                    if txt:
                        preferred_docs.append({"title": name, "url": url, "text": txt})
            if preferred_docs:
                docs.extend(preferred_docs)
                notes["web_added"] += len(preferred_docs)
                done, result = await self._render_if_complete(q, docs)
                if done:
                    notes["citations"] = result[0]["citations"]; return notes, result[1]

        # 4) Resto de la web
        if self.search:
            try:
                hits = await self.search.search(q, count=10)
            except Exception:
                hits = []
            web_docs: List[dict] = []
            for it in hits:
                url = it.get("url"); name = it.get("name","") or ""
                if not url: continue
                txt, from_cache = await cached_fetch_and_clean(url, db_path=self.cache_db, ttl_hours=24*7, return_flag=True)
                if from_cache: notes["cache_hits"] += 1
                if txt:
                    web_docs.append({"title": name, "url": url, "text": txt})
            if web_docs:
                docs.extend(web_docs)
                notes["web_added"] += len(web_docs)

        # Render final (lo que tengamos)
        md, cits = build_structured_markdown(q, docs, self.preferred_domains)
        notes["citations"] = cits
        return notes, md