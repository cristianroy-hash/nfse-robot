from fastapi import FastAPI
from app.routes.importar import router

app = FastAPI(title="NFS-e Robot")
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok", "message": "NFS-e Robot online"}
