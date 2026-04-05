from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

# Removido o import threading, pois usaremos BackgroundTasks do FastAPI

router = APIRouter()
# Dicionário global para armazenar o status dos jobs
jobs = {}

class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    data_inicio: str
    data_fim: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    portal_usuario: Optional[str] = None
    portal_senha: Optional[str] = None

@router.post("/importar-notas")
async def importar_notas(req: ImportRequest, background_tasks: BackgroundTasks):
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
        "notas_encontradas": 0,
        "notas_importadas": 0,
        "message": "Na fila de processamento"
    }

    # --- CORREÇÃO AQUI ---
    # Em vez de thread, usamos background_tasks. 
    # O FastAPI detecta que 'executar_importacao' é async e lida com o 'await' automaticamente.
    background_tasks.add_task(executar_importacao, job_id, req.dict(), jobs)

    return jobs[job_id]

@router.get("/status/{job_id}")
async def status_job(job_id: str):
    if job_id not in jobs:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Job não encontrado"
        }
    return jobs[job_id]
