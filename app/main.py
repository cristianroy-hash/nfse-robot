import logging
logging.basicConfig(level=logging.DEBUG)

from fastapi import FastAPI

try:
    from app.routes.importar import router
    logging.info("Router importado com sucesso")
except Exception as e:
    logging.error(f"Erro ao importar router: {e}")
    router = None

app = FastAPI(title="NFS-e Robot")

if router:
    app.include_router(router)
    logging.info("Router registrado com sucesso")

@app.get("/health")
def health():
    return {"status": "ok", "message": "NFS-e Robot online"}
