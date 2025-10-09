# backend/app.py
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import dotenv_values

# Paquetes internos
from backend.core.pipeline import NOTAPipeline
from backend.core.search_client import SearchClient  # cliente unificado Google/Bing

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
search_client = SearchClient.from_env(cfg)

# 🧠 Pipeline principal (pásale el search_client)
pipe = NOTAPipeline(db_dir=DATA_DIR, search_client=search_client)

class ChatIn(BaseModel):
    q: str

@app.on_event("startup")
async def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    engine = (cfg.get("SEARCH_ENGINE") or "").upper()
    print(f"🔍 SEARCH_ENGINE={engine or 'NONE'} | client={'OK' if search_client else 'NONE'}")
    print(f"📂 DATA_DIR: {os.path.abspath(DATA_DIR)}")

@app.get("/health")
def health():
    return {"ok": True, "time": time.time()}

@app.post("/chat")
async def chat(body: ChatIn):
    notes, answer = await pipe.run(body.q)
    return {"answer": answer, "notes": notes, "citations": notes.get("citations", [])}

# 👇 Endpoints de diagnóstico
@app.get("/debug/env")
def debug_env():
    def mask(v: str | None):
        if not v or v == "missing":
            return v
        return "set"
    return {
        "SEARCH_ENGINE": cfg.get("SEARCH_ENGINE"),
        "GOOGLE_API_KEY": mask(cfg.get("GOOGLE_API_KEY")),
        "GOOGLE_API_KEY_preview": (cfg.get("GOOGLE_API_KEY", "")[:6] + "..." + cfg.get("GOOGLE_API_KEY", "")[-4:]) if cfg.get("GOOGLE_API_KEY") else None,
        "GOOGLE_CX": cfg.get("GOOGLE_CX"),
        "BING_KEY": "set" if cfg.get("BING_KEY") else "missing",
    }

@app.get("/search/test")
async def search_test(q: str, n: int = 5):
    hits = await search_client.search(q, count=n)
    return {"ok": True, "count": len(hits), "items": hits[:n]}