from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid
import asyncio
import os
import zipfile
import io
import shutil

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
# ROTA: IMPORTAR NOTAS
# =========================
@router.post("/importar-notas")
async def importar_notas(req: ImportRequest):
    # Alterado para o caminho de serviço correto
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
    asyncio.create_task(
        executar_importacao(job_id, req.dict(), jobs)
    )
    return {
        "job_id": job_id,
        "status": "queued"
    }

# =========================
# ROTA: STATUS DO JOB
# =========================
@router.get("/status/{job_id}")
async def status_job(job_id: str):
    if job_id not in jobs:
        return {
            "job_id": job_id,
            "status": "not_found",
            "message": "Job não encontrado"
        }
    return jobs[job_id]

# =========================
# ROTA: DOWNLOAD INDIVIDUAL XML
# =========================
@router.post("/baixar-xml")
async def baixar_xml_individual(req: DownloadRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.services.robot_service import baixar_xml # Corrigido import

    if not req.url_download:
        return {"erro": "url_download não informada"}

    download_dir = f"/tmp/xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None
    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )
        
        nota = {
            "chave_acesso": req.chave_acesso,
            "url_download": req.url_download
        }
        
        ok = await baixar_xml(browser_data["page"], nota, download_dir)
        if not ok:
            return {"erro": "Falha ao baixar XML — verifique sessão e URL"}

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.xml")
        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.xml",
            media_type="application/xml"
        )
    finally:
        if browser_data:
            await browser_data["browser"].close()
        # Limpeza opcional: shutil.rmtree(download_dir) - cuidado com FileResponse assíncrono

# =========================
# ROTA: DOWNLOAD INDIVIDUAL DANFSe
# =========================
@router.post("/baixar-danfse")
async def baixar_danfse_individual(req: DownloadRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.services.robot_service import baixar_danfse # Corrigido import

    if not req.url_danfse:
        return {"erro": "url_danfse não informada"}

    download_dir = f"/tmp/danfse_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None
    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )
        
        nota = {
            "chave_acesso": req.chave_acesso,
            "url_danfse": req.url_danfse,
            "data_chave": req.chave_acesso # Fallback para o nome do arquivo
        }
        
        ok = await baixar_danfse(browser_data["page"], nota, download_dir)
        if not ok:
            return {"erro": "Falha ao baixar DANFSe — verifique url_danfse"}

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.pdf")
        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.pdf",
            media_type="application/pdf"
        )
    finally:
        if browser_data:
            await browser_data["browser"].close()

# =========================
# ROTA: DOWNLOAD EM LOTE XML (ZIP)
# =========================
@router.post("/baixar-lote-xml")
async def baixar_lote_xml_route(req: DownloadLoteRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.services.robot_service import baixar_xml # Corrigido import

    if not req.notas:
        return {"erro": "Lista de notas vazia"}

    download_dir = f"/tmp/lote_xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None
    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        sucesso, falha = 0, 0
        for i, nota in enumerate(req.notas):
            nota_dict = nota.dict()
            chave = nota_dict.get("chave_acesso") or nota_dict.get("data_chave", f"nota_{i}")
            print(f"📥 XML lote [{i+1}/{len(req.notas)}] {chave}")
            
            # Garante que as chaves esperadas pelo robot_service existam
            ok = await baixar_xml(browser_data["page"], nota_dict, download_dir)
            if ok:
                sucesso += 1
            else:
                falha += 1
            await asyncio.sleep(1)

        # Compactação em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in os.listdir(download_dir):
                if arquivo.endswith(".xml"):
                    zf.write(os.path.join(download_dir, arquivo), arquivo)
        
        zip_buffer.seek(0)
        
        if zip_buffer.getbuffer().nbytes == 0:
            return {"erro": f"Falha no lote: {falha} erros detectados."}

        # Limpeza do diretório temporário física após zipar
        shutil.rmtree(download_dir)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=notas_xml_{req.cliente_id}.zip"}
        )
    finally:
        if browser_data:
            await browser_data["browser"].close()

# =========================
# ROTA: DOWNLOAD EM LOTE DANFSe (ZIP)
# =========================
@router.post("/baixar-lote-danfse")
async def baixar_lote_danfse_route(req: DownloadLoteRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.services.robot_service import baixar_danfse # Corrigido import

    if not req.notas:
        return {"erro": "Lista de notas vazia"}

    download_dir = f"/tmp/lote_pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser_data = None
    try:
        browser_data = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        sucesso, falha = 0, 0
        for i, nota in enumerate(req.notas):
            nota_dict = nota.dict()
            # Garante compatibilidade de chaves
            if not nota_dict.get("data_chave"):
                nota_dict["data_chave"] = nota_dict.get("chave_acesso")
                
            ok = await baixar_danfse(browser_data["page"], nota_dict, download_dir)
            if ok:
                sucesso += 1
            else:
                falha += 1
            await asyncio.sleep(1)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in os.listdir(download_dir):
                if arquivo.endswith(".pdf"):
                    zf.write(os.path.join(download_dir, arquivo), arquivo)
        
        zip_buffer.seek(0)
        
        if zip_buffer.getbuffer().nbytes == 0:
            return {"erro": "Nenhum PDF baixado."}

        shutil.rmtree(download_dir)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=notas_danfse_{req.cliente_id}.zip"}
        )
    finally:
        if browser_data:
            await browser_data["browser"].close()
