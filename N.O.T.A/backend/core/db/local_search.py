import os
import aiosqlite
from typing import List, Dict

class LocalMedicalSearcher:
    """
    Busca en:
      - FTS conocidas: documents, docs_fts (si existen)
      - learned_knowledge (contenido aprendido)
      - fallback LIKE en tablas normales
    """
    def __init__(self, db_dir: str):
        self.db1 = os.path.join(db_dir, "medical_fts.sqlite")
        self.db2 = os.path.join(db_dir, "output.db")
        self.fts_candidates = ["documents", "docs_fts"]

    async def _table_exists(self, conn, name: str) -> bool:
        async with conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)) as cur:
            return (await cur.fetchone()) is not None

    async def _fts_query(self, conn, db_path: str, q: str, top_k: int) -> List[Dict]:
        rows: List[Dict] = []
        for table in self.fts_candidates:
            if not await self._table_exists(conn, table):
                continue
            # detecta columnas
            async with conn.execute(f"PRAGMA table_info('{table}')") as cur:
                cols = [r[1] for r in await cur.fetchall()]
            pick = []
            for c in ("title", "content", "text"):
                if c in cols: pick.append(c)
            pick = pick or cols[:2]
            select_expr = ", ".join([f'"{c}"' for c in pick]) if pick else "*"

            try:
                sql = f'SELECT rowid, {select_expr} FROM "{table}" WHERE "{table}" MATCH ? LIMIT ?'
                async with conn.execute(sql, (q, top_k)) as cur:
                    fetched = await cur.fetchall()
                for r in fetched:
                    parts = [v if isinstance(v, str) else "" for v in r[1:]]
                    txt = " ".join(parts).strip()
                    if txt:
                        rows.append({"source": os.path.basename(db_path), "title": pick[0] if pick else table, "content": txt})
            except Exception:
                continue
        return rows

    async def _learned_query(self, conn, db_path: str, q: str, top_k: int) -> List[Dict]:
        rows: List[Dict] = []
        if not await self._table_exists(conn, "learned_knowledge"):
            return rows
        sql = """
        SELECT query, summary, sources FROM learned_knowledge
        WHERE query LIKE ? OR summary LIKE ?
        ORDER BY id DESC LIMIT ?
        """
        async with conn.execute(sql, (f"%{q}%", f"%{q}%", top_k)) as cur:
            for row in await cur.fetchall():
                rows.append({"source": os.path.basename(db_path), "title": row[0], "content": row[1]})
        return rows

    async def _like_fallback(self, conn, db_path: str, q: str, top_k: int) -> List[Dict]:
        rows: List[Dict] = []
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
            tables = [r[0] for r in await cur.fetchall()]
        for t in tables:
            if t.startswith("sqlite_") or t.lower().startswith("fts") or t in self.fts_candidates or t == "learned_knowledge":
                continue
            try:
                async with conn.execute(f"PRAGMA table_info('{t}')") as cur:
                    cols = [r[1] for r in await cur.fetchall()]
                if not cols: continue
                where = " OR ".join([f'"{c}" LIKE ?' for c in cols])
                params = tuple([f"%{q}%" for _ in cols] + [top_k])
                sql = f'SELECT * FROM "{t}" WHERE {where} LIMIT ?'
                async with conn.execute(sql, params) as cur:
                    fetched = await cur.fetchall()
                for r in fetched:
                    parts = [v for v in r if isinstance(v, str)]
                    txt = " ".join(parts).strip()
                    if txt:
                        rows.append({"source": os.path.basename(db_path), "title": t, "content": txt})
            except Exception:
                continue
        return rows

    async def search(self, q: str, top_k: int = 8) -> List[Dict]:
        results: List[Dict] = []
        for path in [self.db1, self.db2]:
            if not os.path.exists(path): 
                continue
            async with aiosqlite.connect(path) as conn:
                conn.row_factory = aiosqlite.Row
                hits = await self._fts_query(conn, path, q, top_k)
                if not hits and os.path.basename(path) == "output.db":
                    hits = await self._learned_query(conn, path, q, top_k)
                if not hits:
                    hits = await self._like_fallback(conn, path, q, top_k)
                results.extend(hits)
        return results[:top_k]