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

# -----------------------------------------------------------------------------
# Carga .env + entorno
# -----------------------------------------------------------------------------
cfg = {**dotenv_values("backend/.env"), **os.environ}

DATA_DIR = cfg.get("DATA_DIR", "./backend/data")
ALLOWED = cfg.get("ALLOWED_ORIGINS", "*")

# Bases locales (opcional)
IOS_FTS_DB = cfg.get("IOS_FTS_DB", f"{DATA_DIR.rstrip('/')}/medical_fts.sqlite")
OUTPUT_DB = cfg.get("OUTPUT_DB", f"{DATA_DIR.rstrip('/')}/output.db")

# Dominios preferidos (se priorizan en el ranking y en la búsqueda)
PREFERRED_DOMAINS = [
    d.strip()
    for d in (cfg.get("PREFERRED_DOMAINS", "").split(",") if cfg.get("PREFERRED_DOMAINS") else [])
    if d.strip()
]

# -----------------------------------------------------------------------------
# FastAPI
# -----------------------------------------------------------------------------
app = FastAPI(title="N.O.T.A", version="0.4")

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

# 🧠 Pipeline principal (inyecta search_client + rutas de DB + dominios preferidos)
pipe = NOTAPipeline(
    db_dir=DATA_DIR,
    search_client=search_client,
    ios_fts_db=IOS_FTS_DB,
    output_db=OUTPUT_DB,
    preferred_domains=PREFERRED_DOMAINS,
)

# -----------------------------------------------------------------------------
# Modelos
# -----------------------------------------------------------------------------
class ChatIn(BaseModel):
    q: str

# -----------------------------------------------------------------------------
# Hooks
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)
    engine = (cfg.get("SEARCH_ENGINE") or "").upper()
    print(f"🔍 SEARCH_ENGINE={engine or 'NONE'} | client={'OK' if search_client else 'NONE'}")
    print(f"📂 DATA_DIR: {os.path.abspath(DATA_DIR)}")
    print(f"🗃️ IOS_FTS_DB: {os.path.abspath(IOS_FTS_DB)} | exists={os.path.exists(IOS_FTS_DB)}")
    print(f"🗃️ OUTPUT_DB:  {os.path.abspath(OUTPUT_DB)} | exists={os.path.exists(OUTPUT_DB)}")
    print(f"⭐ Preferidos: {PREFERRED_DOMAINS or '(ninguno)'}")

# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------
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
        "GOOGLE_API_KEY_preview": (cfg.get("GOOGLE_API_KEY", "")[:6] + "..." + cfg.get("GOOGLE_API_KEY", "")[-4:])
            if cfg.get("GOOGLE_API_KEY") else None,
        "GOOGLE_CX": cfg.get("GOOGLE_CX"),
        "BING_KEY": "set" if cfg.get("BING_KEY") else "missing",
        "DATA_DIR": os.path.abspath(DATA_DIR),
        "IOS_FTS_DB": os.path.abspath(IOS_FTS_DB),
        "IOS_FTS_DB_exists": os.path.exists(IOS_FTS_DB),
        "OUTPUT_DB": os.path.abspath(OUTPUT_DB),
        "OUTPUT_DB_exists": os.path.exists(OUTPUT_DB),
        "PREFERRED_DOMAINS": PREFERRED_DOMAINS,
    }

@app.get("/search/test")
async def search_test(q: str, n: int = 5):
    if not search_client:
        return {"ok": False, "error": "search_client no configurado", "items": []}
    try:
        hits = await search_client.search(q, count=n)
    except Exception as e:
        return {"ok": False, "error": str(e), "items": []}
    return {"ok": True, "count": len(hits or []), "items": (hits or [])[:n]}