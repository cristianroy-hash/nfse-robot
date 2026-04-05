from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid
import asyncio

router = APIRouter()

# Armazena status dos jobs
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
async def importar_notas(req: ImportRequest):
    from app.services.import_service import executar_importacao

    job_id = str(uuid.uuid4())

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

    print(f"📩 Novo job recebido: {job_id}")

    # 🔥 EXECUÇÃO ASSÍNCRONA REAL (CORREÇÃO PRINCIPAL)
    asyncio.create_task(
        executar_importacao(job_id, req.dict(), jobs)
    )

    return {
        "job_id": job_id,
        "status": "queued"
    }


@router.get("/status/{job_id}")
async def status_job(job_id: str):
    if job_id not in jobs:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Job não encontrado"
        }

    return jobs[job_id]
