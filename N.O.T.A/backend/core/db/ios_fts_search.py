# backend/core/db/ios_fts_search.py
from __future__ import annotations
import sqlite3
from typing import List, Dict

DDL = """
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY,
  title   TEXT,
  url     TEXT,
  section TEXT,
  content TEXT
);

-- Índices útiles si no usas FTS
CREATE INDEX IF NOT EXISTS idx_documents_title   ON documents(title);
CREATE INDEX IF NOT EXISTS idx_documents_url     ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_section ON documents(section);

-- Tabla FTS opcional (si la DB ya la trae, esto no se ejecutará por falta de permisos o ya existe)
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
  title, url, section, content,
  content='documents', content_rowid='id',
  tokenize='unicode61'
);

-- Triggers (no hacen daño si la DB es sólo lectura; se crearán si procede)
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON documents BEGIN
  INSERT INTO docs_fts(rowid, title, url, section, content)
  VALUES (new.id, new.title, new.url, new.section, new.content);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON documents BEGIN
  INSERT INTO docs_fts(docs_fts, rowid, title, url, section, content)
  VALUES ('delete', old.id, old.title, old.url, old.section, old.content);
END;
CREATE TRIGGER IF NOT EXISTS docs_au AFTER UPDATE ON documents BEGIN
  INSERT INTO docs_fts(docs_fts, rowid, title, url, section, content)
  VALUES ('delete', old.id, old.title, old.url, old.section, old.content);
  INSERT INTO docs_fts(rowid, title, url, section, content)
  VALUES (new.id, new.title, new.url, new.section, new.content);
END;
"""

def _open(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # performance y compat
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

def _ensure_schema(con: sqlite3.Connection) -> None:
    try:
        con.executescript(DDL)
        con.commit()
    except Exception:
        # Si la DB es estrictamente de solo lectura o ya trae su propio esquema, ignoramos
        pass

class IOSFTSSearcher:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def search(self, q: str, top_k: int = 10) -> List[Dict]:
        if not q.strip():
            return []
        try:
            con = _open(self.db_path)
        except Exception as e:
            print(f"[WARN] No se pudo abrir IOS_FTS_DB ({self.db_path}): {e}")
            return []

        try:
            _ensure_schema(con)

            # Preferir FTS si existe
            try:
                rows = con.execute(
                    """
                    SELECT d.id, d.title, d.url, d.section, d.content
                    FROM docs_fts f
                    JOIN documents d ON d.id = f.rowid
                    WHERE docs_fts MATCH ?
                    LIMIT ?
                    """,
                    (q, top_k)
                ).fetchall()
            except sqlite3.OperationalError:
                # Fallback a LIKE si no hay FTS
                try:
                    rows = con.execute(
                        """
                        SELECT id, title, url, section, content
                        FROM documents
                        WHERE title LIKE ? OR content LIKE ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (f"%{q}%", f"%{q}%", top_k)
                    ).fetchall()
                except sqlite3.OperationalError as e2:
                    # Esquema realmente ausente: no rompas, solo avisa
                    print(f"[WARN] IOS_FTS_DB sin tablas esperadas: {e2}")
                    rows = []
        finally:
            con.close()

        out: List[Dict] = []
        for r in rows:
            out.append({
                "id": r["id"],
                "title": r["title"],
                "url": r["url"],
                "section": r["section"],
                "content": r["content"],
            })
        return out