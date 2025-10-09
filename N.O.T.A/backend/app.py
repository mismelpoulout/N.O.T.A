# backend/app.py
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import dotenv_values

# ✅ Importa con el paquete 'backend'
from backend.core.pipeline import NOTAPipeline
from backend.core.search_client import SearchClient  # <- cliente unificado (Google/Bing)

# Carga .env + entorno
cfg = {**dotenv_values("backend/.env"), **os.environ}

DATA_DIR = cfg.get("DATA_DIR", "./backend/data")
ALLOWED = cfg.get("ALLOWED_ORIGINS", "*")

app = FastAPI(title="N.O.T.A", version="0.3")

# CORS
allow_origins = ["*"] if ALLOWED == "*" else [o.strip() for o in ALLOWED.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔎 Motor de búsqueda (elige por SEARCH_ENGINE=google | bing)
search_client = SearchClient()

# 🧠 Pipeline principal
pipe = NOTAPipeline(db_dir=DATA_DIR, search_client=search_client)

class ChatIn(BaseModel):
    q: str

@app.on_event("startup")
async def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

@app.get("/health")
def health():
    return {"ok": True, "time": time.time()}

@app.post("/chat")
async def chat(body: ChatIn):
    notes, answer = await pipe.run(body.q)
    return {"answer": answer, "notes": notes, "citations": notes.get("citations", [])}

# 👇 Endpoint de prueba para el motor de búsqueda (sin pasar por todas las capas)
@app.get("/search/test")
async def search_test(q: str):
    hits = await search_client.search(q, count=5)
    return {"ok": True, "count": len(hits), "items": hits[:5]}