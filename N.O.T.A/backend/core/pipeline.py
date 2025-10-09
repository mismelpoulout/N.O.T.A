# backend/core/pipeline.py
from __future__ import annotations
from typing import Tuple, List, Dict
import aiosqlite
from datetime import datetime

from backend.core.rag.store import VectorStore
from backend.core.rag.ingest import Embedder, chunk
from backend.core.rag.retrieve import Retriever
from backend.core.rag.compose import build_context, summarize_extractivo

from backend.core.db.local_search import LocalMedicalSearcher
from backend.core.cleaners import fetch_and_clean
from backend.core.search_client import SearchClient   # <— tu wrapper (Google o Bing)

class NOTAPipeline:
    def __init__(self, db_dir: str = "./backend/data", search_client: SearchClient | None = None):
        self.db_dir = db_dir
        self.search_client = search_client
        self.learned_db = f"{db_dir}/output.db"
        self.vstore = VectorStore(f"{db_dir}/vector.sqlite")
        self.emb = Embedder(model="BAAI/bge-small-en-v1.5")   # ligero y funciona bien
        self.retriever = Retriever(self.vstore, self.emb)
        self.local = LocalMedicalSearcher(db_dir)

    async def _ensure(self):
        await self.vstore.init()

    async def run(self, q: str) -> Tuple[Dict, str]:
        await self._ensure()
        notes = {"query_norm": q, "citations": [], "local_added": 0, "web_added": 0}

        # 1) Fuente local “clásica” → ingerimos al vector-store si aún no existe (on demand).
        local_hits = await self.local.search(q, top_k=8)
        for h in local_hits:
            await self._upsert_if_new(
                doc_id=h.get("doc_id") or h.get("id") or "local",
                source="db",
                text=h["content"],
                url=h.get("url")
            )
        notes["local_added"] = len(local_hits)

        # 2) Si tenemos motor web activo, buscar y **aprender** (ingesta web).
        if self.search_client and self.search_client.impl:
            web = await self.search_client.search(q, count=6)
            cleaned = []
            for it in web:
                url = it.get("url")
                if not url: continue
                txt = await fetch_and_clean(url)
                if not txt: continue
                await self._upsert_if_new(doc_id=url, source="web", text=txt, url=url, meta={"title": it.get("name")})
                cleaned.append(url)
            notes["web_added"] = len(cleaned)

        # 3) Recuperación por embeddings (RAG)
        matches = await self.retriever.similar(q, top_k=8)
        context, cites = build_context(matches, max_chars=2200)
        notes["citations"] = cites

        # 4) Resumen/Respuesta
        if not context.strip():
            answer = (
                f"**Pregunta:** {q}\n\n"
                f"**Resumen:**\nNo se encontró información en la base local ni en la web (o no hay motor de búsqueda configurado)."
            )
            return notes, answer

        answer = llm.generate(prompt_with_context)
        answer = f"**Pregunta:** {q}\n\n**Resumen (RAG):**\n{summary}\n\n**Referencias:**\n" + "\n".join(cites)
        return notes, answer

    async def _upsert_if_new(self, doc_id: str, source: str, text: str, url: str | None = None, meta: Dict | None = None):
        # Trocear + embeber + guardar (siempre se inserta; si quieres, puedes evitar duplicados con UNIQUE(doc_id, chunk_id))
        chunks = chunk(text)
        vecs = self.emb.encode(chunks)
        rows = []
        for i, (t, v) in enumerate(zip(chunks, vecs)):
            rows.append({
                "doc_id": doc_id,
                "chunk_id": i,
                "text": t,
                "url": url,
                "source": source,
                "meta": meta or {},
                "emb": v
            })
        await self.vstore.upsert(rows)