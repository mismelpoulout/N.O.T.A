# backend/core/pipeline.py
import aiosqlite
from typing import List, Tuple, Dict, Any
from datetime import datetime
import re

# ✅ Imports usando el paquete backend completo
from backend.core.db.local_search import LocalMedicalSearcher
from backend.core.cleaners import fetch_and_clean


def summarize(query: str, docs: List[str], max_sentences: int = 6) -> str:
    """
    Capa 4️⃣ — Resumen extractivo:
    Divide el texto en frases, pondera por frecuencia de términos de la consulta,
    y devuelve las mejores frases en orden de aparición.
    """
    if not docs:
        return "No hay contenido para resumir."
    text = "\n".join(docs)
    sents = re.split(r'(?<=[\.\!\?])\s+', text)
    terms = [t.lower() for t in re.findall(r'\w+', query) if len(t) > 2]
    scored = []
    for i, s in enumerate(sents):
        ls = s.lower()
        score = sum(ls.count(t) for t in terms)
        scored.append((score, i, s.strip()))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top_sorted = sorted([(i, s) for (_, i, s) in scored[:max_sentences]], key=lambda x: x[0])
    return " ".join(s for _, s in top_sorted).strip()


class NOTAPipeline:
    """
    🧠 Flujo principal de N.O.T.A (5 capas):
      1️⃣ Análisis de la consulta
      2️⃣ Búsqueda en la base local → Web (Google o Bing)
      3️⃣ Recopilación y limpieza
      4️⃣ Resumen
      5️⃣ Respuesta y aprendizaje (guarda conocimiento)
    """

    def __init__(
        self,
        db_dir: str = "./backend/data",
        search_client=None,
        bing_client=None
    ):
        # Capas base
        self.searcher = LocalMedicalSearcher(db_dir)
        self.search = search_client or bing_client
        self.output_db = f"{db_dir}/output.db"

    async def run(self, q: str) -> Tuple[Dict[str, Any], str]:
        # 1️⃣ Análisis de la consulta
        q = q.strip()
        notes = {
            "query_norm": q,
            "local_hits": 0,
            "web_hits": 0,
            "saved": False,
            "citations": [],
        }

        if not q:
            return notes, "⚠️ Pregunta vacía."

        # 2️⃣ Búsqueda en base local
        local = await self.searcher.search(q, top_k=8)
        notes["local_hits"] = len(local)
        local_texts = [r["content"] for r in local]

        if local_texts:
            summary = summarize(q, local_texts, max_sentences=6)
            answer = (
                f"**Pregunta:** {q}\n\n"
                f"**Resumen (base local / aprendizaje previo):**\n{summary}"
            )
            return notes, answer

        # 3️⃣ Búsqueda Web (Google o Bing)
        web_docs = []
        if self.search:
            try:
                web = await self.search.search(q, count=6)
            except Exception as e:
                return notes, f"⚠️ Error de búsqueda web: {e}"

            cleaned_docs = []
            for it in web:
                url = it.get("url")
                if not url:
                    continue
                txt = await fetch_and_clean(url)
                if not txt:
                    continue
                cleaned_docs.append(
                    {"title": it.get("name", ""), "url": url, "text": txt}
                )

            notes["web_hits"] = len(cleaned_docs)
            notes["citations"] = [d["url"] for d in cleaned_docs][:6]
            web_docs = [d["text"] for d in cleaned_docs]

            # 4️⃣ Resumen y 5️⃣ Aprendizaje
            if cleaned_docs:
                merged_summary = summarize(q, web_docs, max_sentences=7)
                await self._save_learning(q, merged_summary, cleaned_docs)
                notes["saved"] = True
                answer = (
                    f"**Pregunta:** {q}\n\n"
                    f"**Resumen (web):**\n{merged_summary}\n\n"
                    f"**Referencias:**\n" + "\n".join(notes["citations"])
                )
                return notes, answer

        # 🔚 Si no hay resultados
        answer = (
            f"**Pregunta:** {q}\n\n"
            f"**Resumen:**\nNo se encontró información en la base local ni en la web "
            f"(o no hay motor de búsqueda configurado)."
        )
        return notes, answer

    async def _save_learning(self, q: str, summary: str, docs: List[dict]) -> None:
        """
        Guarda conocimiento aprendido:
        - Resúmenes en `learned_knowledge`
        - Páginas completas en `learned_pages`
        """
        async with aiosqlite.connect(self.output_db) as db:
            # Crear tablas si no existen
            await db.execute("""
                CREATE TABLE IF NOT EXISTS learned_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT,
                    summary TEXT,
                    sources TEXT,
                    created_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS learned_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    created_at TEXT
                )
            """)

            # Insertar / actualizar páginas
            for d in docs:
                try:
                    await db.execute("""
                        INSERT INTO learned_pages (url, title, content, created_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(url) DO UPDATE SET
                            title = excluded.title,
                            content = excluded.content
                    """, (
                        d["url"],
                        d.get("title", ""),
                        d["text"],
                        datetime.utcnow().isoformat(),
                    ))
                except Exception:
                    pass

            # Insertar resumen general
            srcs = ", ".join([d["url"] for d in docs if d.get("url")])
            await db.execute("""
                INSERT INTO learned_knowledge (query, summary, sources, created_at)
                VALUES (?, ?, ?, ?)
            """, (q, summary, srcs, datetime.utcnow().isoformat()))
            await db.commit()