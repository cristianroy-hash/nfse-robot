import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid
import asyncio
import zipfile
import io
import shutil

# =========================
# IMPORTS (PADRONIZADOS)
# =========================
from app.services.browser_service import criar_browser_com_certificado
from app.services.robot_service import baixar_xml, baixar_danfse
from app.services.import_service import executar_importacao

router = APIRouter()

# Armazena status dos jobs
jobs = {}

# =========================
# MODELS
# =========================
class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    data_inicio: str
    data_fim: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    portal_usuario: Optional[str] = None
    portal_senha: Optional[str] = None

class DownloadRequest(BaseModel):
    cliente_id: str
    chave_acesso: str
    url_download: Optional[str] = None  
    url_danfse: Optional[str] = None    
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

class NotaLote(BaseModel):
    chave_acesso: Optional[str] = None
    data_chave: Optional[str] = None
    url_download: Optional[str] = None  
    url_danfse: Optional[str] = None    

class DownloadLoteRequest(BaseModel):
    cliente_id: str
    notas: List[NotaLote]
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

# =========================
# ROTAS
# =========================

@router.post("/importar-notas")
async def importar_notas(req: ImportRequest):
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

    asyncio.create_task(executar_importacao(job_id, req.dict(), jobs))

    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
async def status_job(job_id: str):
    return jobs.get(job_id, {"job_id": job_id, "status": "not_found"})


@router.post("/baixar-xml")
async def baixar_xml_individual(req: DownloadRequest):
    if not req.url_download:
        raise HTTPException(status_code=400, detail="url_download ausente")

    download_dir = f"/tmp/xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None

    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        ok = await baixar_xml(browser_data["page"], req.dict(), download_dir)

        if not ok:
            raise HTTPException(status_code=500, detail="Falha ao baixar XML")

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.xml")

        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.xml",
            media_type="application/xml"
        )

    finally:
        if browser_data:
            await browser_data["browser"].close()


@router.post("/baixar-danfse")
async def baixar_danfse_individual(req: DownloadRequest):
    if not req.url_danfse:
        raise HTTPException(status_code=400, detail="url_danfse ausente")

    download_dir = f"/tmp/pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None

    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        req_dict = req.dict()
        req_dict["data_chave"] = req.chave_acesso  # Compatibilidade

        ok = await baixar_danfse(browser_data["page"], req_dict, download_dir)

        if not ok:
            raise HTTPException(status_code=500, detail="Falha ao baixar DANFSE")

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.pdf")

        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.pdf",
            media_type="application/pdf"
        )

    finally:
        if browser_data:
            await browser_data["browser"].close()


@router.post("/baixar-lote-xml")
async def baixar_lote_xml_route(req: DownloadLoteRequest):
    download_dir = f"/tmp/lote_xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None

    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        for nota in req.notas:
            await baixar_xml(browser_data["page"], nota.dict(), download_dir)
            await asyncio.sleep(0.5)  # leve melhoria de performance

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(download_dir):
                zf.write(os.path.join(download_dir, f), f)

        zip_buffer.seek(0)
        shutil.rmtree(download_dir)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=xml_{req.cliente_id}.zip"
            }
        )

    finally:
        if browser_data:
            await browser_data["browser"].close()


@router.post("/baixar-lote-danfse")
async def baixar_lote_danfse_route(req: DownloadLoteRequest):
    download_dir = f"/tmp/lote_pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None

    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        for nota in req.notas:
            n = nota.dict()

            if not n.get("data_chave"):
                n["data_chave"] = n.get("chave_acesso")

            await baixar_danfse(browser_data["page"], n, download_dir)
            await asyncio.sleep(0.5)  # leve melhoria

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(download_dir):
                zf.write(os.path.join(download_dir, f), f)

        zip_buffer.seek(0)
        shutil.rmtree(download_dir)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=danfse_{req.cliente_id}.zip"
            }
        )

    finally:
        if browser_data:
            await browser_data["browser"].close()
