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
import httpx  # Para baixar o PDF direto via URL

# ============================================================
# IMPORTS (CORRIGIDOS PARA ESTRUTURA DE PASTAS)
# ============================================================
try:
    from ..robot.browser import criar_browser_com_certificado
    from ..robot.consultar import baixar_xml
    from ..services.import_service import executar_importacao
except (ImportError, ValueError):
    from app.robot.browser import criar_browser_com_certificado
    from app.robot.consultar import baixar_xml
    from app.services.import_service import executar_importacao

router = APIRouter()
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

class DownloadRequest(BaseModel):
    cliente_id: str
    chave_acesso: str
    url_download: Optional[str] = None  
    url_danfse: Optional[str] = None    
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

class NotaLote(BaseModel):
    chave_acesso: Optional[str] = None
    url_download: Optional[str] = None  
    url_danfse: Optional[str] = None    

class DownloadLoteRequest(BaseModel):
    cliente_id: str
    notas: List[NotaLote]
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

# =========================
# ROTAS - IMPORTAÇÃO
# =========================

@router.post("/importar-notas")
async def importar_notas(req: ImportRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id, "status": "queued", "cliente_id": req.cliente_id,
        "notas_encontradas": 0, "notas_importadas": 0, "message": "Na fila"
    }
    asyncio.create_task(executar_importacao(job_id, req.dict(), jobs))
    return {"job_id": job_id, "status": "queued"}

@router.get("/status/{job_id}")
async def status_job(job_id: str):
    return jobs.get(job_id, {"job_id": job_id, "status": "not_found"})

# =========================
# ROTAS - XML (USA O ROBÔ)
# =========================

@router.post("/baixar-xml")
async def baixar_xml_individual(req: DownloadRequest):
    if not req.certificado_base64:
        raise HTTPException(status_code=400, detail="Certificado necessário para XML")
    
    download_dir = f"/tmp/xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    browser_data = None

    try:
        # Chama o robô exatamente como o import_service faz
        browser_data = await criar_browser_com_certificado(req.certificado_base64, req.certificado_senha)
        
        ok = await baixar_xml(browser_data["page"], req.dict(), download_dir)
        
        if not ok:
            raise HTTPException(status_code=500, detail="Portal recusou o download do XML")

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.xml")
        return FileResponse(path=caminho, filename=f"{req.chave_acesso}.xml", media_type="application/xml")
    finally:
        if browser_data:
            await browser_data["browser"].close()

@router.post("/baixar-lote-xml")
async def baixar_lote_xml_route(req: DownloadLoteRequest):
    if not req.certificado_base64:
        raise HTTPException(status_code=400, detail="Certificado necessário para XML")
        
    download_dir = f"/tmp/lote_xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    browser_data = None

    try:
        browser_data = await criar_browser_com_certificado(req.certificado_base64, req.certificado_senha)
        for nota in req.notas:
            if nota.url_download:
                await baixar_xml(browser_data["page"], nota.dict(), download_dir)
                await asyncio.sleep(0.5)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(download_dir):
                zf.write(os.path.join(download_dir, f), f)
        
        zip_buffer.seek(0)
        return StreamingResponse(zip_buffer, media_type="application/zip", 
                                 headers={"Content-Disposition": f"attachment; filename=xml_lote.zip"})
    finally:
        if browser_data:
            await browser_data["browser"].close()
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir)

# =========================
# ROTAS - PDF (DIRETO VIA URL - SEM ROBÔ)
# =========================

async def download_pdf_direto(url: str, caminho: str):
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        if r.status_code == 200:
            with open(caminho, 'wb') as f:
                f.write(r.content)
            return True
    return False

@router.post("/baixar-danfse")
async def baixar_danfse_individual(req: DownloadRequest):
    # URL Direta: https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave=...
    url = f"https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave={req.chave_acesso}"
    
    download_dir = f"/tmp/pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    caminho = os.path.join(download_dir, f"{req.chave_acesso}.pdf")

    if await download_pdf_direto(url, caminho):
        return FileResponse(path=caminho, filename=f"{req.chave_acesso}.pdf", media_type="application/pdf")
    
    raise HTTPException(status_code=500, detail="Erro ao obter PDF do portal público")

@router.post("/baixar-lote-danfse")
async def baixar_lote_danfse_route(req: DownloadLoteRequest):
    download_dir = f"/tmp/lote_pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    try:
        for nota in req.notas:
            chave = nota.chave_acesso
            url = f"https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave={chave}"
            caminho = os.path.join(download_dir, f"{chave}.pdf")
            await download_pdf_direto(url, caminho)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(download_dir):
                zf.write(os.path.join(download_dir, f), f)

        zip_buffer.seek(0)
        return StreamingResponse(zip_buffer, media_type="application/zip", 
                                 headers={"Content-Disposition": "attachment; filename=pdf_lote.zip"})
    finally:
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir)
