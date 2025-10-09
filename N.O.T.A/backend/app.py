# backend/app.py
import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import dotenv_values

from backend.core.pipeline import NOTAPipeline
from backend.core.search_client import SearchClient

cfg = {**dotenv_values("backend/.env"), **os.environ}

DATA_DIR = cfg.get("DATA_DIR", "./backend/data")
ALLOWED = cfg.get("ALLOWED_ORIGINS", "*")
ENGINE = (cfg.get("SEARCH_ENGINE") or "google").lower()

app = FastAPI(title="N.O.T.A", version="0.3")

allow_origins = ["*"] if ALLOWED == "*" else [o.strip() for o in ALLOWED.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# motor de búsqueda desde .env
search_client = SearchClient.from_env(cfg)
print(f"🔍 SEARCH_ENGINE={ENGINE.upper()} | client={'OK' if search_client.impl else 'None'}")

pipe = NOTAPipeline(db_dir=DATA_DIR, search_client=search_client)

class ChatIn(BaseModel):
    q: str

@app.on_event("startup")
async def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"📂 DATA_DIR: {os.path.abspath(DATA_DIR)}")

@app.get("/health")
def health():
    return {"ok": True, "time": time.time()}

@app.post("/chat")
async def chat(body: ChatIn):
    notes, answer = await pipe.run(body.q)
    return {"answer": answer, "notes": notes, "citations": notes.get("citations", [])}

# Debug opcional
@app.get("/debug/env")
def debug_env():
    masked = (cfg.get("GOOGLE_API_KEY") or cfg.get("GOOGLE_KEY") or "")
    if masked:
        masked = masked[:6] + "..." + masked[-4:]
    return {
        "SEARCH_ENGINE": ENGINE,
        "GOOGLE_API_KEY": "set" if masked else "missing",
        "GOOGLE_API_KEY_preview": masked,
        "GOOGLE_CX": cfg.get("GOOGLE_CX"),
        "BING_KEY": "set" if cfg.get("BING_KEY") else "missing",
    }