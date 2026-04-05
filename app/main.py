from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.routes.importar import router

app = FastAPI(title="NFS-e Robot", version="1.0.0")


# =========================
# CORS (ajustado)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois você pode restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# ROTAS
# =========================
app.include_router(router)


# =========================
# STARTUP / SHUTDOWN
# =========================
@app.on_event("startup")
async def startup_event():
    print("🚀 API NFS-e Robot iniciada com sucesso")


@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 API finalizando...")


# =========================
# HEALTH CHECK
# =========================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "message": "NFS-e Robot online"
    }


# =========================
# ROOT (DEBUG)
# =========================
@app.get("/")
async def root():
    return {
        "message": "API NFS-e Robot funcionando",
        "docs": "/docs",
        "health": "/health"
    }
