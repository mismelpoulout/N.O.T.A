# -*- coding: utf-8 -*-
import os, sqlite3, hashlib
from pathlib import Path

DB_PATH   = "backend/data/books.db"
BOOKS_DIR = "backend/data/pdfs"

os.makedirs(BOOKS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# --- Detecta extractor disponible: fitz (PyMuPDF) o pypdf ---
_EXTRACTOR = None
try:
    import fitz  # PyMuPDF
    def _extract_text_with_fitz(path: str) -> str:
        doc = fitz.open(path)
        parts = []
        for page in doc:
            txt = page.get_text("text")
            if txt and txt.strip():
                parts.append(txt)
        return "\n".join(parts)
    _EXTRACTOR = ("pymupdf", _extract_text_with_fitz)
except Exception:
    try:
        from pypdf import PdfReader
        def _extract_text_with_pypdf(path: str) -> str:
            reader = PdfReader(path)
            parts = []
            for page in reader.pages:
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    txt = ""
                if txt.strip():
                    parts.append(txt)
            return "\n".join(parts)
        _EXTRACTOR = ("pypdf", _extract_text_with_pypdf)
    except Exception:
        _EXTRACTOR = None

if _EXTRACTOR is None:
    raise SystemExit(
        "❌ No hay extractor PDF disponible. Instala uno:\n"
        "   pip install 'PyMuPDF==1.24.10'   # si usas Python 3.12\n"
        "   pip install 'pypdf==4.3.1'       # extractor puro-Python (sirve en 3.13)\n"
    )

NAME, EXTRACT = _EXTRACTOR
print(f"🔎 Extractor PDF activo: {NAME}")

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS book_chunks(
            id TEXT PRIMARY KEY,
            book_title TEXT,
            path TEXT,
            chunk TEXT
        )
    """)
    # Índices útiles
    con.execute("CREATE INDEX IF NOT EXISTS idx_book_chunks_title ON book_chunks(book_title)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_book_chunks_path  ON book_chunks(path)")
    con.commit()
    return con

def chunk_text(text: str, size: int = 1500, overlap: int = 200):
    words = text.split()
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i+size]))
        i += max(1, size - overlap)
    return out

def ingest():
    con  = init_db()
    cur  = con.cursor()
    pdfs = list(Path(BOOKS_DIR).glob("*.pdf"))
    if not pdfs:
        print(f"ℹ️ No se encontraron PDFs en {BOOKS_DIR}. Copia tus libros ahí.")
        return

    for pdf in pdfs:
        try:
            text = EXTRACT(str(pdf))
        except Exception as e:
            print(f"⚠️ Error extrayendo {pdf.name}: {e}")
            continue

        if not (text and text.strip()):
            print(f"⚠️ Vacío o sin texto extraíble: {pdf.name}")
            continue

        chunks = chunk_text(text)
        inserted = 0
        for c in chunks:
            cid = hashlib.md5((pdf.stem + c[:100]).encode("utf-8", "ignore")).hexdigest()
            cur.execute(
                "INSERT OR IGNORE INTO book_chunks(id, book_title, path, chunk) VALUES(?,?,?,?)",
                (cid, pdf.stem, str(pdf), c)
            )
            if cur.rowcount:
                inserted += 1
        con.commit()
        print(f"✅ {pdf.name}: {inserted} chunks añadidos.")

    con.close()
    print(f"🎉 Ingesta completada. DB: {DB_PATH}")

if __name__ == "__main__":
    ingest()