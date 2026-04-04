from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter()

class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    competencia: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

@router.post("/importar-notas")
def importar_notas(req: ImportRequest):
    job_id = str(uuid.uuid4())
    return {
        "job_id": job_id,
        "status": "queued",
        "cliente_id": req.cliente_id,
        "competencia": req.competencia
    }
