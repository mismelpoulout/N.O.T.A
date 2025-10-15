# backend/core/rag/retrieve.py
from __future__ import annotations
from typing import List, Dict, Any
import numpy as np
from backend.core.rag.ingest import Embedder
from backend.core.rag.store import VectorStore

class Retriever:
    def __init__(self, store: VectorStore, embedder: Embedder):
        self.store = store
        self.emb = embedder

    async def similar(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        qvec = self.emb.encode([query])[0]
        return await self.store.topk(qvec, k=top_k)