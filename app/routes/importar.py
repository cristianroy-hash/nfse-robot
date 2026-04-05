from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid
import threading

router = APIRouter()
jobs = {}

class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    competencia: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    portal_usuario: Optional[str] = None
    portal_senha: Optional[str] = None

@router.post("/importar-notas")
def importar_notas(req: ImportRequest):
    from app.services.import_service import executar_importacao
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "cliente_id": req.cliente_id,
        "competencia": req.competencia,
        "notas_importadas": 0,
        "message": ""
    }

    thread = threading.Thread(
        target=executar_importacao,
        args=(job_id, req.dict(), jobs)
    )
    thread.start()

    return jobs[job_id]

@router.get("/status/{job_id}")
def status_job(job_id: str):
    if job_id not in jobs:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Job não encontrado"
        }
    return jobs[job_id]
