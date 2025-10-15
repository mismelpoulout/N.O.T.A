# backend/core/embed_books.py
import sqlite3, json, os
from google import genai  # si usas el SDK oficial de Gemini
from tqdm import tqdm

DB_PATH = "backend/data/books.db"

def embed_all():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Falta GEMINI_API_KEY en entorno")

    client = genai.Client(api_key=api_key)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    con.execute("""
        CREATE TABLE IF NOT EXISTS embeddings(
            id TEXT PRIMARY KEY,
            vector TEXT
        )
    """)
    con.commit()

    rows = con.execute("SELECT id, chunk FROM book_chunks").fetchall()
    for r in tqdm(rows):
        try:
            emb = client.embed_content(model="models/text-embedding-004", content=r["chunk"])
            vector = emb["embedding"]
            con.execute("INSERT OR REPLACE INTO embeddings(id, vector) VALUES(?,?)", (r["id"], json.dumps(vector)))
        except Exception as e:
            print("Error con chunk:", r["id"], e)
    con.commit()
    con.close()
    print("✅ Embeddings generados y guardados.")

if __name__ == "__main__":
    embed_all()