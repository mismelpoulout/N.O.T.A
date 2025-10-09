# backend/core/pipeline.py
from __future__ import annotations
from typing import List, Tuple
from datetime import datetime
import aiosqlite

from backend.core.db.local_search import LocalMedicalSearcher
from backend.core.cleaners import fetch_and_clean

def summarize_extractivo(query: str, docs: List[str], max_sentences: int = 6) -> str:
    import re
    if not docs: return "No hay contenido para resumir."
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
    def __init__(self, db_dir: str = "./backend/data", search_client=None):
        self.searcher = LocalMedicalSearcher(db_dir)
        self.search_client = search_client
        self.output_db = f"{db_dir}/output.db"

    async def run(self, q: str) -> Tuple[dict, str]:
        q = q.strip()
        notes = {"query_norm": q, "citations": [], "local_added": 0, "web_added": 0}
        if not q:
            return notes, "⚠️ Pregunta vacía."

        # 1) Local
        local = await self.searcher.search(q, top_k=8)
        if local:
            notes["local_added"] = len(local)
            summary = summarize_extractivo(q, [r["content"] for r in local], max_sentences=6)
            return notes, f"**Pregunta:** {q}\n\n**Resumen (base local):**\n{summary}"

        # 2) Web
        cleaned_docs = []
        if self.search_client:
            try:
                hits = await self.search_client.search(q, count=6)
            except Exception:
                hits = []
            for it in hits or []:
                url = it.get("url") or it.get("link")
                if not url:
                    continue
                try:
                    txt = await fetch_and_clean(url)
                except Exception:
                    txt = None
                if not txt:
                    continue
                cleaned_docs.append({"title": it.get("name",""), "url": url, "text": txt})

        notes["web_added"] = len(cleaned_docs)
        if cleaned_docs:
            notes["citations"] = [d["url"] for d in cleaned_docs][:6]
            merged_summary = summarize_extractivo(q, [d["text"] for d in cleaned_docs], max_sentences=7)
            await self._save_learning(q, merged_summary, cleaned_docs)
            answer = (
                f"**Pregunta:** {q}\n\n"
                f"**Resumen (web):**\n{merged_summary}\n\n"
                f"**Referencias:**\n" + "\n".join(notes["citations"])
            )
            return notes, answer

        return notes, (
            f"**Pregunta:** {q}\n\n"
            f"**Resumen:**\nNo se encontró información en la base local ni en la web (motor sin configurar o limpieza fallida)."
        )

    async def _save_learning(self, q: str, summary: str, docs: List[dict]) -> None:
        async with aiosqlite.connect(self.output_db) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS learned_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT, summary TEXT, sources TEXT, created_at TEXT
            )""")
            await db.execute("""CREATE TABLE IF NOT EXISTS learned_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE, title TEXT, content TEXT, created_at TEXT
            )""")
            for d in docs:
                await db.execute("""
                    INSERT INTO learned_pages (url, title, content, created_at)
                    VALUES (?,?,?,?)
                    ON CONFLICT(url) DO UPDATE SET title=excluded.title, content=excluded.content
                """, (d["url"], d.get("title",""), d["text"], datetime.utcnow().isoformat()))
            srcs = ", ".join([d["url"] for d in docs if d.get("url")])
            await db.execute("""
                INSERT INTO learned_knowledge (query, summary, sources, created_at)
                VALUES (?,?,?,?)
            """, (q, summary, srcs, datetime.utcnow().isoformat()))
            await db.commit()