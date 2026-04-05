from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid
import threading

router = APIRouter()
# Dicionário global para armazenar o status dos jobs (em produção, o ideal é Redis ou BD)
jobs = {}

class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    # Substituído competencia por data_inicio e data_fim para alinhar com o HTML
    data_inicio: str
    data_fim: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    portal_usuario: Optional[str] = None
    portal_senha: Optional[str] = None

@router.post("/importar-notas")
def importar_notas(req: ImportRequest):
    # Importação local para evitar importação circular
    from app.services.import_service import executar_importacao
    
    job_id = str(uuid.uuid4())
    
    # Inicializa o status do job no dicionário
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "cliente_id": req.cliente_id,
        "data_inicio": req.data_inicio,
        "data_fim": req.data_fim,
        "notas_importadas": 0,
        "message": "Na fila de processamento"
    }

    # Dispara a thread do robô
    # req.dict() enviará todos os campos (incluindo as novas datas) para o serviço
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
