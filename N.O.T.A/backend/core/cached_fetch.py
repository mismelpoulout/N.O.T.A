# backend/core/cached_fetch.py
from __future__ import annotations
import sqlite3, time
from typing import Optional, Tuple
from backend.core.cleaners import fetch_and_clean  # async

DEFAULT_TTL_HOURS = 24*7

def _ensure(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS pages(
            url TEXT PRIMARY KEY,
            fetched_at REAL NOT NULL,
            content TEXT
        )
    """)
    con.commit(); con.close()

async def cached_fetch_and_clean(url: str, db_path: str, ttl_hours: int = DEFAULT_TTL_HOURS, return_flag: bool = False) -> (str|None) | Tuple[Optional[str], bool]:
    _ensure(db_path)
    now = time.time(); ttl = ttl_hours*3600

    con = sqlite3.connect(db_path)
    try:
        cur = con.execute("SELECT content, fetched_at FROM pages WHERE url=?", (url,))
        row = cur.fetchone()
        if row:
            content, fetched_at = row
            if (now - fetched_at) < ttl and content:
                con.close()
                return (content, True) if return_flag else content
    finally:
        try: con.close()
        except: pass

    try:
        txt = await fetch_and_clean(url)
    except Exception as e:
        print(f"[WARN] fetch_and_clean fail {url}: {e}")
        txt = None

    con = sqlite3.connect(db_path)
    try:
        con.execute("REPLACE INTO pages(url, fetched_at, content) VALUES(?,?,?)", (url, now, txt or ""))
        con.commit()
    finally:
        con.close()

    return (txt or "", False) if return_flag else (txt or "")