from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from app.routes.importar import router
import os

app = FastAPI(title="NFS-e Robot")

API_KEY = os.environ.get("ROBOT_API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key")

async def verificar_api_key(key: str = Security(api_key_header)):
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="API Key inválida")
    return key

app.include_router(router, dependencies=[Security(verificar_api_key)])

@app.get("/health")
def health():
    return {"status": "ok", "message": "NFS-e Robot online"}
