# backend/core/rag/store.py
from __future__ import annotations
import aiosqlite, json, numpy as np
from typing import List, Dict, Any, Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS passages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT,
  chunk_id INTEGER,
  text TEXT,
  url TEXT,
  source TEXT,   -- 'db' | 'web' | 'learned'
  meta TEXT,     -- json
  emb BLOB
);
CREATE INDEX IF NOT EXISTS idx_doc ON passages(doc_id);
"""

def _to_blob(v: np.ndarray) -> bytes:
    return v.astype(np.float32).tobytes()

def _from_blob(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)

class VectorStore:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()

    async def upsert(self, rows: List[Dict[str, Any]]):
        if not rows: return
        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                "INSERT INTO passages (doc_id, chunk_id, text, url, source, meta, emb) VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        r.get("doc_id"),
                        r.get("chunk_id", 0),
                        r["text"],
                        r.get("url"),
                        r.get("source","learned"),
                        json.dumps(r.get("meta") or {}),
                        _to_blob(r["emb"]),
                    )
                    for r in rows
                ],
            )
            await db.commit()

    async def topk(self, qvec: np.ndarray, k: int = 8) -> List[Dict[str, Any]]:
        # Scan simple (suficiente para miles). Si crece, migramos a FAISS.
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT id, text, url, source, meta, emb FROM passages")
            out = []
            async for row in cur:
                emb = _from_blob(row[5])
                # coseno
                denom = (np.linalg.norm(qvec) * np.linalg.norm(emb)) or 1.0
                score = float(np.dot(qvec, emb) / denom)
                out.append((score, row))
            out.sort(key=lambda t: t[0], reverse=True)
            res = []
            for s, r in out[:k]:
                res.append({
                    "id": r[0], "text": r[1], "url": r[2], "source": r[3],
                    "meta": json.loads(r[4] or "{}"), "score": s
                })
            return res