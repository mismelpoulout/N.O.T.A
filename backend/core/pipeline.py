import os, re, json, sqlite3, time
from typing import List, Dict, Tuple, Optional

import numpy as np

from .embeddings import LocalEmbeddings, cosine_sim
from .clin_sections import ClinSectionClassifier
from .negation import is_negated
from .ranker import Ranker, Hit
from .llm_client import LLMClient

PREF = set(d.strip() for d in os.getenv("PREFERRED_DOMAINS", "").split(",") if d.strip())

_MIN_SENT_LEN = 40
_MAX_SENT_LEN = 400

# Mapea etiquetas de tu clasificador a encabezados “canónicos” del prompt
SECTION_CANON = {
    "definicion": "Motivo / Contexto",
    "sintomas": "Síntomas",
    "diagnostico": "Diagnóstico",
    "examen": "Examen",
    "tratamiento": "Plan",
    "conducta": "Plan",
    "otros": "Otros",
}

def _split_sentences(text: str) -> List[str]:
    """
    Split por puntuación fuerte, limpia URLs, normaliza espacios
    y restringe por longitud para evitar ruido.
    """
    if not text:
        return []
    s = re.sub(r"\s+", " ", text)
    s = re.sub(r"https?://\S+", "", s)
    # Cortes por . ! ? seguidos de espacio+mayúscula típica en ES
    parts = re.split(r"(?<=[\.\!\?])\s+(?=[A-ZÁÉÍÓÚÜÑ])", s)
    out = []
    seen = set()
    for p in parts:
        p = p.strip().strip(". ")
        if len(p) < _MIN_SENT_LEN or len(p) > _MAX_SENT_LEN:
            continue
        key = re.sub(r"[^a-z0-9áéíóúüñ ]", "", p.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out

def _canon_label(label: Optional[str]) -> str:
    return SECTION_CANON.get((label or "otros"), "Otros")

class NOTAPipeline:
    """
    RAG local sobre SQLite:
      - Tabla chunks(id TEXT PRIMARY KEY, text TEXT, meta TEXT NULL)
      - Tabla embeddings(chunk_id TEXT PRIMARY KEY, dim INT, vec BLOB)
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.emb = LocalEmbeddings()
        self.cls = ClinSectionClassifier(self.emb)
        self.rank = Ranker(self.emb, PREF)
        self.llm = LLMClient()

    # ------------------- Recuperación local -------------------
    def _load_all_embeddings(self) -> Tuple[List[str], List[str], Optional[np.ndarray], List[dict]]:
        """
        Devuelve: ids, texts, mat_emb (N x D) o None si vacío, metas (dict por chunk)
        meta soporta claves opcionales: title, book_title, path, url, source, published_at
        """
        try:
            con = sqlite3.connect(self.db_path)
            cur = con.cursor()
            # meta (JSON) es opcional; si no existe la columna, caemos al SELECT sin meta
            try:
                cur.execute("""
                    SELECT e.chunk_id, e.dim, e.vec, c.text, c.meta
                    FROM embeddings e
                    JOIN chunks c ON c.id = e.chunk_id
                """)
                rows = cur.fetchall()
            except sqlite3.OperationalError:
                cur.execute("""
                    SELECT e.chunk_id, e.dim, e.vec, c.text
                    FROM embeddings e
                    JOIN chunks c ON c.id = e.chunk_id
                """)
                rows = [(cid, dim, vec, txt, None) for (cid, dim, vec, txt) in cur.fetchall()]
        except sqlite3.Error:
            return [], [], None, []
        finally:
            try:
                con.close()
            except Exception:
                pass

        ids, texts, vecs, metas = [], [], [], []
        for cid, dim, blob, txt, meta_raw in rows:
            if blob is None:
                continue
            v = np.frombuffer(blob, dtype=np.float32)
            if v.shape[0] != int(dim or 0):
                continue
            ids.append(str(cid))
            texts.append(txt or "")
            vecs.append(v)
            meta = {}
            if meta_raw:
                try:
                    meta = json.loads(meta_raw)
                except Exception:
                    meta = {}
            metas.append(meta)
        if not vecs:
            return [], [], None, []
        return ids, texts, np.stack(vecs, axis=0), metas

    def _source_from_meta(self, cid: str, meta: dict) -> str:
        # Elige la mejor “firma” de fuente disponible
        for k in ("url", "source", "path"):
            val = (meta or {}).get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # Títulos útiles
        title = (meta or {}).get("title") or (meta or {}).get("book_title")
        if title:
            return f"local:{title}"
        return f"local:chunk:{cid}"

    def _top_by_embedding(self, query: str, topn: int = 40) -> List[Hit]:
        ids, texts, vecs, metas = self._load_all_embeddings()
        if vecs is None or not ids:
            return []
        qv = self.emb.embed([query])[0]  # (D,)
        sims = cosine_sim(vecs, qv[None, :]).ravel()
        order = np.argsort(-sims)[:topn]
        out: List[Hit] = []
        for i in order:
            cid = ids[i]
            src = self._source_from_meta(cid, metas[i] if i < len(metas) else {})
            out.append(Hit(chunk_id=cid, text=texts[i], source=src))
        return out

    # ------------------- Pipeline principal -------------------
    async def run(self, q: str):
        q = (q or "").strip()
        if not q:
            return {"error": "empty_query"}, "⚠️ Pregunta vacía."

        # 1) recuperar candidatos por embedding
        hits = self._top_by_embedding(q, topn=60)
        if not hits:
            # Sin base local: evita alucinaciones. Pide refinar datos.
            answer = (
                "No encuentro contenido local aún indexado para responder con confianza. "
                "Carga PDFs en la base o habilita búsqueda web, y vuelve a intentar."
            )
            notes = {"sections": [], "citations": [], "used_sentences": 0}
            return notes, answer

        # 2) partir en oraciones, clasificar, marcar negaciones
        sents: List[str] = []
        parents: List[Hit] = []
        for h in hits:
            for s in _split_sentences(h.text):
                sents.append(s)
                parents.append(h)

        if not sents:
            notes = {"sections": [], "citations": list({h.source for h in hits if h.source}), "used_sentences": 0}
            return notes, "No pude extraer oraciones útiles de los documentos locales."

        labels = self.cls.predict(sents)
        sent_hits: List[Hit] = []
        for s, ph, lab in zip(sents, parents, labels):
            sent_hits.append(
                Hit(
                    chunk_id=ph.chunk_id,
                    text=s,
                    source=ph.source,
                    section=_canon_label(lab),
                    negated=is_negated(s),
                )
            )

        # 3) rerank con tu Ranker (MMR + boosts por dominio preferido / recencia si lo aplicas ahí)
        top = self.rank.rerank(q, sent_hits, k=18)

        # 4) agrupar y preparar evidencia ordenada por sección
        by_sec: Dict[str, List[str]] = {}
        for h in top:
            sec = h.section or "Otros"
            # (opcional) Si no quieres oraciones negadas en “Síntomas”, podrías filtrarlas:
            # if sec == "Síntomas" and h.negated: continue
            by_sec.setdefault(sec, []).append(h.text)

        # Recorta por sección para el prompt
        def _bulletize(lines: List[str], n: int) -> List[str]:
            out, seen = [], set()
            for t in lines:
                key = re.sub(r"[^a-z0-9áéíóúüñ ]", "", t.lower())
                if key in seen:
                    continue
                seen.add(key)
                out.append(f"- {t.strip().rstrip('.')}.")
                if len(out) >= n:
                    break
            return out

        evidence_md = []
        for sec, lines in by_sec.items():
            bullets = _bulletize(lines, 6)
            if not bullets:
                continue
            evidence_md.append(f"### {sec}\n" + "\n".join(bullets))

        # 5) Prompt para LLM (controlado y en español)
        system = (
            "Eres un asistente clínico. Responde SOLO con la evidencia proporcionada. "
            "Evita contradicciones; si hay conflicto, explica la incertidumbre. "
            "Responde en español y organiza en secciones con títulos claros: "
            "Motivo / Contexto, Síntomas, Examen, Diagnóstico, Plan. "
            "Sé conciso y clínicamente útil."
        )
        user = f"Pregunta: {q}\n\nEVIDENCIA LOCAL (resumen por secciones):\n\n" + "\n\n".join(evidence_md)

        answer = await self.llm.complete(system, user)

        notes = {
            "sections": [sec for sec, lines in by_sec.items() if lines],
            "citations": sorted(list({h.source for h in top if h.source})),
            "used_sentences": sum(len(v) for v in by_sec.values()),
            "generated_at": time.time(),
        }
        return notes, answer