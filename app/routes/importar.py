from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uuid
import asyncio
import os
import zipfile
import io

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

# NOVO: modelo para download individual de XML ou DANFSe
class DownloadRequest(BaseModel):
    cliente_id: str
    chave_acesso: str
    url_download: Optional[str] = None  # URL do XML (Emissor Nacional)
    url_danfse: Optional[str] = None    # URL do DANFSe (portal público)
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None

# NOVO: modelo para download em lote (ZIP)
class NotaLote(BaseModel):
    chave_acesso: Optional[str] = None
    data_chave: Optional[str] = None
    url_download: Optional[str] = None  # URL do XML
    url_danfse: Optional[str] = None    # URL do DANFSe

class DownloadLoteRequest(BaseModel):
    cliente_id: str
    notas: List[NotaLote]
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None


# =========================
# ROTA: IMPORTAR NOTAS (original — sem alteração)
# =========================
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
    asyncio.create_task(
        executar_importacao(job_id, req.dict(), jobs)
    )
    return {
        "job_id": job_id,
        "status": "queued"
    }


# =========================
# ROTA: STATUS DO JOB (original — sem alteração)
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
# NOVO: ROTA — DOWNLOAD INDIVIDUAL XML
# Abre sessão autenticada com certificado e baixa o XML da nota.
# Retorna o arquivo .xml diretamente para o browser.
# =========================
@router.post("/baixar-xml")
async def baixar_xml_individual(req: DownloadRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.consultar import baixar_xml

    if not req.url_download:
        return {"erro": "url_download não informada"}

    # NOVO: cria diretório temporário para o arquivo
    download_dir = f"/tmp/xml_{req.chave_acesso}"
    os.makedirs(download_dir, exist_ok=True)

    browser = None
    try:
        # NOVO: abre browser com certificado para autenticar no portal
        browser, page = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )
        nota = {
            "chave_acesso": req.chave_acesso,
            "url_download": req.url_download
        }
        ok = await baixar_xml(page, nota, download_dir)
        if not ok:
            return {"erro": "Falha ao baixar XML — verifique sessão e URL"}

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.xml")
        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.xml",
            media_type="application/xml"
        )
    finally:
        if browser:
            await browser.close()


# =========================
# NOVO: ROTA — DOWNLOAD INDIVIDUAL DANFSe (PDF oficial)
# Acessa o portal público sem autenticação e baixa o PDF.
# Retorna o arquivo .pdf diretamente para o browser.
# =========================
@router.post("/baixar-danfse")
async def baixar_danfse_individual(req: DownloadRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.consultar import baixar_danfse

    if not req.url_danfse:
        return {"erro": "url_danfse não informada"}

    download_dir = f"/tmp/danfse_{req.chave_acesso}"
    os.makedirs(download_dir, exist_ok=True)

    browser = None
    try:
        # NOVO: browser com certificado necessário mesmo para portal público
        # pois o Playwright precisa de contexto válido para fazer o fetch/download
        browser, page = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )
        nota = {
            "chave_acesso": req.chave_acesso,
            "url_danfse": req.url_danfse
        }
        ok = await baixar_danfse(page, nota, download_dir)
        if not ok:
            return {"erro": "Falha ao baixar DANFSe — verifique url_danfse"}

        caminho = os.path.join(download_dir, f"{req.chave_acesso}.pdf")
        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.pdf",
            media_type="application/pdf"
        )
    finally:
        if browser:
            await browser.close()


# =========================
# NOVO: ROTA — DOWNLOAD EM LOTE XML (retorna ZIP)
# Abre sessão autenticada, baixa todos os XMLs e empacota em ZIP.
# Retorna o arquivo .zip via streaming para o browser.
# =========================
@router.post("/baixar-lote-xml")
async def baixar_lote_xml_route(req: DownloadLoteRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.consultar import baixar_xml

    if not req.notas:
        return {"erro": "Lista de notas vazia"}

    download_dir = f"/tmp/lote_xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser = None
    try:
        browser, page = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        sucesso, falha = 0, 0
        for i, nota in enumerate(req.notas):
            nota_dict = nota.dict()
            chave = nota_dict.get("chave_acesso") or nota_dict.get("data_chave", f"nota_{i}")
            print(f"📥 XML lote [{i+1}/{len(req.notas)}] {chave}")
            ok = await baixar_xml(page, nota_dict, download_dir)
            if ok:
                sucesso += 1
            else:
                falha += 1
            # NOVO: pequena pausa entre downloads para não sobrecarregar o portal
            await asyncio.sleep(1)

        print(f"✅ Lote XML: {sucesso} ok / {falha} falhas")

        # NOVO: compacta todos os XMLs baixados em um ZIP em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in os.listdir(download_dir):
                if arquivo.endswith(".xml"):
                    zf.write(os.path.join(download_dir, arquivo), arquivo)
        zip_buffer.seek(0)

        if zip_buffer.getbuffer().nbytes == 0:
            return {"erro": "Nenhum XML foi baixado com sucesso"}

        nome_zip = f"notas_xml_{req.cliente_id}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={nome_zip}"}
        )
    finally:
        if browser:
            await browser.close()


# =========================
# NOVO: ROTA — DOWNLOAD EM LOTE DANFSe (retorna ZIP)
# Baixa todos os PDFs oficiais via portal público e empacota em ZIP.
# Por ser portal público, não exige autenticação — mas usa browser
# para manter consistência e suporte a fetch/download via Playwright.
# =========================
@router.post("/baixar-lote-danfse")
async def baixar_lote_danfse_route(req: DownloadLoteRequest):
    from app.services.browser_service import criar_browser_com_certificado
    from app.consultar import baixar_danfse

    if not req.notas:
        return {"erro": "Lista de notas vazia"}

    download_dir = f"/tmp/lote_danfse_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    browser = None
    try:
        browser, page = await criar_browser_com_certificado(
            req.certificado_base64,
            req.certificado_senha
        )

        sucesso, falha = 0, 0
        for i, nota in enumerate(req.notas):
            nota_dict = nota.dict()
            chave = nota_dict.get("chave_acesso") or nota_dict.get("data_chave", f"nota_{i}")
            print(f"📥 DANFSe lote [{i+1}/{len(req.notas)}] {chave}")
            ok = await baixar_danfse(page, nota_dict, download_dir)
            if ok:
                sucesso += 1
            else:
                falha += 1
            # NOVO: pausa entre downloads para não sobrecarregar o portal público
            await asyncio.sleep(1)

        print(f"✅ Lote DANFSe: {sucesso} ok / {falha} falhas")

        # NOVO: compacta todos os PDFs em um ZIP em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for arquivo in os.listdir(download_dir):
                if arquivo.endswith(".pdf"):
                    zf.write(os.path.join(download_dir, arquivo), arquivo)
        zip_buffer.seek(0)

        if zip_buffer.getbuffer().nbytes == 0:
            return {"erro": "Nenhum DANFSe foi baixado com sucesso"}

        nome_zip = f"notas_danfse_{req.cliente_id}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={nome_zip}"}
        )
    finally:
        if browser:
            await browser.close()
