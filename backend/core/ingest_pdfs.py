import os, json, sqlite3, sys
from pathlib import Path
from tqdm import tqdm
import numpy as np

from .embeddings import LocalEmbeddings
from .utils_pdf import sha256_file

DATA_DIR = Path(os.getenv("DATA_DIR", "./backend/data"))
PDF_DIR  = DATA_DIR / "pdfs"
DB_PATH  = Path(os.getenv("SQLITE_DB", "./backend/data/medical.db"))
JSONL    = Path(os.getenv("CORPUS_JSONL", "./backend/data/corpus.jsonl"))

def extract_text_pdf(path: Path) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        txt = "\n".join([p.get_text("text") for p in doc])
        return txt
    except Exception:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return "\n".join([p.extract_text() or "" for p in r.pages])

def split_into_chunks(text: str, size=900, overlap=150):
    words = text.split()
    i, chunks = 0, []
    while i < len(words):
        chunk = " ".join(words[i:i+size]).strip()
        if chunk:
            chunks.append(chunk)
        i += size - overlap
    return chunks

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY,
  title TEXT,
  path TEXT,
  sha256 TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY,
  doc_id INTEGER,
  text TEXT,
  section TEXT,
  FOREIGN KEY(doc_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS embeddings(
  chunk_id INTEGER PRIMARY KEY,
  dim INTEGER,
  vec BLOB,
  FOREIGN KEY(chunk_id) REFERENCES chunks(id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks
USING fts5(text, content='chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO fts_chunks(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO fts_chunks(fts_chunks, rowid, text) VALUES('delete', old.id, old.text);
END;
"""

def to_blob(vec: np.ndarray) -> bytes:
    assert vec.dtype == np.float32
    return vec.tobytes(order="C")

def ingest():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(PDF_DIR, exist_ok=True)

    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cur = con.cursor()

    emb = LocalEmbeddings()
    with open(JSONL, "w", encoding="utf-8") as jf:
        for pdf in tqdm(sorted(PDF_DIR.glob("*.pdf"))):
            raw = extract_text_pdf(pdf)
            if not raw.strip(): continue
            sha = sha256_file(pdf)
            cur.execute("INSERT OR IGNORE INTO documents(title, path, sha256) VALUES(?,?,?)",
                        (pdf.stem, str(pdf), sha))
            cur.execute("SELECT id FROM documents WHERE sha256=?", (sha,))
            doc_id = cur.fetchone()[0]

            chunks = split_into_chunks(raw)
            if not chunks: continue

            # JSONL export
            for ch in chunks:
                jf.write(json.dumps({"doc": pdf.stem, "path": str(pdf), "text": ch}, ensure_ascii=False) + "\n")

            # Insert chunks
            cur.executemany("INSERT INTO chunks(doc_id, text, section) VALUES(?,?,NULL)",
                            [(doc_id, ch, ) for ch in chunks])
            con.commit()

            # Fetch ids recién insertados
            cur.execute("SELECT id, text FROM chunks WHERE doc_id=? ORDER BY id DESC LIMIT ?",
                        (doc_id, len(chunks)))
            rows = cur.fetchall()[::-1]  # preservar orden

            # Embeddings
            vecs = emb.embed([t for _, t in rows]).astype(np.float32)
            dim  = int(vecs.shape[1])
            cur.executemany("INSERT OR REPLACE INTO embeddings(chunk_id, dim, vec) VALUES(?,?,?)",
                            [(cid, dim, to_blob(vecs[i])) for i, (cid, _) in enumerate(rows)])
            con.commit()

    con.close()
    print(f"✅ Ingesta completada.\nJSONL: {JSONL}\nDB: {DB_PATH}")

if __name__ == "__main__":
    ingest()