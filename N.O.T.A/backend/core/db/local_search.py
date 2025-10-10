# backend/core/db/local_search.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import aiosqlite
import sqlite3
from typing import List, Dict

SQLITE_MAGIC = b"SQLite format 3\x00"

def _is_sqlite_file(path: str) -> bool:
    try:
        if not os.path.isfile(path) or os.path.getsize(path) < 100:
            return False
        with open(path, "rb") as f:
            return f.read(16) == SQLITE_MAGIC
    except Exception:
        return False

class LocalMedicalSearcher:
    """
    Busca en *.sqlite bajo db_dir. Ignora archivos no-SQLite y maneja
    gracefully las bases corruptas. Espera una tabla FTS (o fallback LIKE).
    """
    def __init__(self, db_dir: str):
        self.db_dir = db_dir

    async def _table_exists(self, conn: aiosqlite.Connection, name: str) -> bool:
        try:
            async with conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,)
            ) as cur:
                row = await cur.fetchone()
                return bool(row)
        except Exception:
            return False

    async def _fts_query(self, conn: aiosqlite.Connection, table: str, q: str, top_k: int) -> List[Dict]:
        # Intenta FTS
        try:
            if await self._table_exists(conn, table):
                sql = f"""
                SELECT title, url, content
                FROM {table}
                WHERE {table} MATCH ?
                ORDER BY rank
                LIMIT ?"""
                async with conn.execute(sql, (q, top_k)) as cur:
                    rows = await cur.fetchall()
                    return [{"title": r[0] or "", "url": r[1] or "", "content": r[2] or ""} for r in rows]
        except Exception:
            pass

        # Fallback: tabla "documents" (no FTS) con LIKE
        try:
            if await self._table_exists(conn, "documents"):
                sql = """
                SELECT title, url, content
                FROM documents
                WHERE title LIKE ? OR content LIKE ?
                ORDER BY id DESC
                LIMIT ?"""
                async with conn.execute(sql, (f"%{q}%", f"%{q}%", top_k)) as cur:
                    rows = await cur.fetchall()
                    return [{"title": r[0] or "", "url": r[1] or "", "content": r[2] or ""} for r in rows]
        except Exception:
            pass

        return []

    async def search(self, q: str, top_k: int = 10) -> List[Dict]:
        out: List[Dict] = []
        if not self.db_dir or not os.path.isdir(self.db_dir):
            return out

        # Recorre solo archivos .sqlite / .db que sean SQLite válidos
        candidates = [
            os.path.join(self.db_dir, f)
            for f in os.listdir(self.db_dir)
            if f.lower().endswith((".sqlite", ".db"))
        ]

        for path in candidates:
            if not _is_sqlite_file(path):
                # Ignora archivos corruptos o que no son SQLite
                continue
            try:
                async with aiosqlite.connect(path) as conn:
                    # nombres comunes para FTS; ajusta si usas otro
                    for table in ("medical_fts", "notes_fts", "fts", "doc_fts"):
                        hits = await self._fts_query(conn, table, q, top_k)
                        if hits:
                            out.extend(hits)
                            break
                    # si no hubo hits en FTS, _fts_query ya intentó fallback LIKE
                    if not out:
                        # último intento por si solo existe "documents" y no devolvió nada
                        hits = await self._fts_query(conn, "documents", q, top_k)
                        out.extend(hits)
            except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
                # No rompas la API por una base rota
                print(f"[WARN] local_search: {os.path.basename(path)} ignorada ({e})")
                continue
            except Exception as e:
                print(f"[WARN] local_search: error inesperado en {path}: {e}")
                continue

        return out[:top_k]