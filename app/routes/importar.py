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
import httpx

# ============================================================
# IMPORTS (mantém o try/except original para compatibilidade
# com diferentes estruturas de pastas no deploy)
# ============================================================
try:
    from ..robot.browser import criar_browser_com_certificado
    from ..robot.consultar import baixar_xml
    from ..services.import_service import executar_importacao
except (ImportError, ValueError):
    from app.robot.browser import criar_browser_com_certificado
    from app.robot.consultar import baixar_xml
    from app.services.import_service import executar_importacao

# ============================================================
# [NOVO v2] IMPORT DO SCRAPER MUNICIPAL (Atende.Net)
# Adicionado para suporte a portais municipais de São José,
# Palhoça e Biguaçu via scraping com usuário/senha.
# O try/except segue o mesmo padrão dos imports acima para
# garantir compatibilidade com diferentes estruturas de deploy.
# ============================================================
try:
    from ..robot.atende_scraper import importar_via_atende, is_portal_atende
except (ImportError, ValueError):
    from app.robot.atende_scraper import importar_via_atende, is_portal_atende

router = APIRouter()

# Armazena status dos jobs em memória (resetado a cada deploy)
jobs = {}


# =========================
# HELPER INTERNO: DESEMPACOTAR RETORNO DO BROWSER
# criar_browser_com_certificado retorna uma TUPLA:
#   (p, browser, context, page, cert_path, key_path)
# Esta função centraliza o desempacotamento para não repetir
# o índice em cada rota e facilitar manutenção futura.
# =========================
def _unpack_browser(browser_tuple):
    p, browser, context, page, cert_path, key_path = browser_tuple
    return p, browser, context, page, cert_path, key_path


# =========================
# HELPER INTERNO: FECHAR BROWSER E LIMPAR TEMPORÁRIOS
# Chamado sempre no bloco finally de cada rota que abre browser.
# Fecha o browser e remove os arquivos PEM temporários do certificado.
# =========================
async def _fechar_browser(browser_tuple):
    try:
        _, browser, _, _, cert_path, key_path = browser_tuple
        await browser.close()
        for path in [cert_path, key_path]:
            if path and os.path.exists(path):
                os.remove(path)
    except Exception as e:
        print(f"⚠️ Erro ao fechar browser: {e}")


# =========================
# HELPER INTERNO: DOWNLOAD DE PDF VIA HTTPX (SEM ROBÔ)
# O portal público gov.br não exige autenticação para DANFSe.
# O robô faz o GET direto — sem CORS, pois é server-side.
# Valida a assinatura %PDF- antes de salvar para evitar HTML de erro.
# Retorna True se o PDF foi salvo com sucesso, False caso contrário.
# =========================
async def _download_pdf_direto(url: str, caminho: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200 and r.content[:4] == b'%PDF':
                with open(caminho, 'wb') as f:
                    f.write(r.content)
                return True
            print(f"⚠️ PDF inválido ou status {r.status_code} para {url}")
    except Exception as e:
        print(f"⚠️ Erro httpx ao baixar PDF: {e}")
    return False


# =========================
# HELPER INTERNO: AQUECER SESSÃO NO PORTAL
# Problema identificado no lote XML: o browser é criado do zero
# (sem histórico de sessão) e vai direto ao download sem login.
# O baixar_xml usa fetch com credentials:'include', mas sem uma
# sessão ativa no portal o servidor retorna HTML de login, não XML.
# Esta função navega para o portal e aguarda o login via certificado
# — exatamente como o import_service faz antes de qualquer download.
# Retorna True se a sessão foi estabelecida, False caso contrário.
# =========================
async def _aquecer_sessao(page) -> bool:
    try:
        print("🔐 Aquecendo sessão no portal NFS-e...")
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=90000
        )
        await page.wait_for_timeout(5000)

        # Se redirecionou para login, clica no botão de certificado
        if await page.locator("#datainicio").count() == 0:
            print(f"↪️ Redirecionado para login. URL: {page.url}")
            btn_cert = page.locator(
                "a[href*='Certificado'], button:has-text('Certificado')"
            ).first
            if await btn_cert.count() > 0:
                print("🖱️ Clicando em autenticar com Certificado...")
                await btn_cert.click()
                await page.wait_for_timeout(8000)
                # Redireciona novamente para a página de notas após login
                await page.goto(
                    "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
                    wait_until="networkidle",
                    timeout=60000
                )
                await page.wait_for_timeout(3000)
            else:
                print("❌ Botão de certificado não encontrado na tela de login")
                return False

        # Confirma que o campo de data está visível (sessão estabelecida)
        if await page.locator("#datainicio").count() > 0:
            print("✅ Sessão estabelecida com sucesso")
            return True

        print("❌ Sessão não estabelecida — campo #datainicio não encontrado")
        return False

    except Exception as e:
        print(f"❌ Erro ao aquecer sessão: {e}")
        return False


# =========================
# MODELS — IMPORTAÇÃO
# [NOVO v2] Adicionados 3 campos opcionais ao final do model:
#   portal_url      → URL do portal municipal Atende.Net
#   portal_usuario  → usuário de acesso ao portal municipal
#   portal_senha    → senha de acesso ao portal municipal
# Todos opcionais (None) para manter retrocompatibilidade total
# com clientes que usam certificado A1 (fluxo original intacto).
# =========================
class ImportRequest(BaseModel):
    cliente_id: str
    cnpj: str
    data_inicio: str
    data_fim: str
    certificado_base64: Optional[str] = None
    certificado_senha: Optional[str] = None
    # [NOVO v2] Credenciais para portais municipais Atende.Net
    portal_url: Optional[str] = None      # ex: https://nfse-saojose.atende.net/...
    portal_usuario: Optional[str] = None  # usuário cadastrado no portal municipal
    portal_senha: Optional[str] = None    # senha cadastrada no portal municipal


# =========================
# MODELS — DOWNLOAD INDIVIDUAL
# =========================
class DownloadRequest(BaseModel):
    cliente_id: str
    chave_acesso: str
    url_download: Optional[str] = None  # URL do XML (Emissor Nacional, requer sessão)
    url_danfse:   Optional[str] = None  # URL do DANFSe (portal público, sem sessão)
    certificado_base64: Optional[str] = None
    certificado_senha:  Optional[str] = None


# =========================
# MODELS — DOWNLOAD EM LOTE
# data_chave: token encodado capturado do data-chave do portal (usado na url_danfse)
# =========================
class NotaLote(BaseModel):
    chave_acesso: Optional[str] = None
    data_chave:   Optional[str] = None  # token encodado do portal (para url_danfse)
    url_download: Optional[str] = None  # URL do XML
    url_danfse:   Optional[str] = None  # URL completa do DANFSe (já montada pelo robô)

class DownloadLoteRequest(BaseModel):
    cliente_id: str
    notas: List[NotaLote]
    certificado_base64: Optional[str] = None
    certificado_senha:  Optional[str] = None


# =========================
# ROTA: IMPORTAR NOTAS (original — sem alteração)
# =========================
@router.post("/importar-notas")
async def importar_notas(req: ImportRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id, "status": "queued",
        "cliente_id": req.cliente_id,
        "notas_encontradas": 0, "notas_importadas": 0,
        "message": "Na fila"
    }
    print(f"📩 Novo job recebido: {job_id}")
    asyncio.create_task(executar_importacao(job_id, req.dict(), jobs))
    return {"job_id": job_id, "status": "queued"}


# =========================
# ROTA: STATUS DO JOB (original — sem alteração)
# =========================
@router.get("/status/{job_id}")
async def status_job(job_id: str):
    return jobs.get(job_id, {"job_id": job_id, "status": "not_found"})


# =========================
# ROTA: DOWNLOAD INDIVIDUAL — XML
# Abre browser com certificado, baixa o XML da nota e retorna o arquivo.
# CORREÇÃO: desempacota a tupla corretamente com _unpack_browser()
# em vez de acessar como dicionário (browser_data["page"]).
# Também usa _aquecer_sessao() antes do download para garantir
# que o portal reconheça o certificado antes do fetch.
# =========================
@router.post("/baixar-xml")
async def baixar_xml_individual(req: DownloadRequest):
    if not req.certificado_base64:
        raise HTTPException(status_code=400, detail="Certificado necessário para baixar XML")
    if not req.url_download:
        raise HTTPException(status_code=400, detail="URL de download não informada")

    download_dir = f"/tmp/xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    browser_tuple = None

    try:
        browser_tuple = await criar_browser_com_certificado(
            req.certificado_base64, req.certificado_senha
        )
        # CORREÇÃO: desempacota tupla corretamente
        _, _, _, page, _, _ = _unpack_browser(browser_tuple)

        # CORREÇÃO SESSÃO: garante sessão autenticada antes do download
        sessao_ok = await _aquecer_sessao(page)
        if not sessao_ok:
            raise HTTPException(
                status_code=500,
                detail="Não foi possível autenticar no portal NFS-e. Verifique o certificado."
            )

        nota_dict = {"chave_acesso": req.chave_acesso, "url_download": req.url_download}
        caminho = os.path.join(download_dir, f"{req.chave_acesso}.xml")

        ok = await baixar_xml(page, nota_dict, download_dir)
        if not ok or not os.path.exists(caminho):
            raise HTTPException(status_code=500, detail="Falha ao baixar XML")

        return FileResponse(
            path=caminho,
            filename=f"{req.chave_acesso}.xml",
            media_type="application/xml"
        )
    finally:
        if browser_tuple:
            await _fechar_browser(browser_tuple)


# =========================
# ROTA: DOWNLOAD EM LOTE — XML (retorna ZIP)
# CORREÇÃO: desempacota a tupla corretamente.
# O shutil.rmtree fica no finally mas APÓS o StreamingResponse
# ser gerado — por isso copiamos o zip para memória antes.
#
# CORREÇÃO SESSÃO (v8→v9): o browser era criado do zero e ia
# direto ao download sem passar pelo login do portal. O portal
# retornava HTML de redirecionamento para login em vez do XML.
# Agora _aquecer_sessao() navega para o portal e estabelece a
# sessão via certificado antes de iniciar o loop de downloads.
#
# CORREÇÃO ZIP VAZIO (v8): a verificação anterior usava
# zip_buffer.getbuffer().nbytes == 0, mas um ZIP vazio já
# ocupa ~22 bytes (cabeçalho), então nunca disparava.
# Agora verificamos a contagem real de arquivos dentro do ZIP.
# =========================
@router.post("/baixar-lote-xml")
async def baixar_lote_xml_route(req: DownloadLoteRequest):
    if not req.certificado_base64:
        raise HTTPException(status_code=400, detail="Certificado necessário para baixar XMLs")

    download_dir = f"/tmp/lote_xml_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    browser_tuple = None

    try:
        browser_tuple = await criar_browser_com_certificado(
            req.certificado_base64, req.certificado_senha
        )
        # CORREÇÃO: desempacota tupla corretamente
        _, _, _, page, _, _ = _unpack_browser(browser_tuple)

        # CORREÇÃO SESSÃO: estabelece sessão autenticada no portal antes
        # de iniciar os downloads — sem isso o portal rejeita os fetches
        sessao_ok = await _aquecer_sessao(page)
        if not sessao_ok:
            raise HTTPException(
                status_code=500,
                detail="Não foi possível autenticar no portal NFS-e. Verifique o certificado."
            )

        sucesso, falha = 0, 0

        # 🔥 MELHORIA PERFORMANCE: adiciona paralelismo controlado (mantendo estrutura original)
        semaphore = asyncio.Semaphore(5)

        async def _baixar_com_controle(nota):
            nonlocal sucesso, falha

            if not nota.url_download:
                falha += 1
                return

            nota_dict = {"chave_acesso": nota.chave_acesso, "url_download": nota.url_download}

            async with semaphore:
                ok = await baixar_xml(page, nota_dict, download_dir)

            if ok:
                sucesso += 1
            else:
                falha += 1

        # 🔥 MELHORIA PERFORMANCE: substitui loop sequencial por execução paralela controlada
        tasks = [_baixar_com_controle(nota) for nota in req.notas]
        await asyncio.gather(*tasks)

        print(f"✅ Lote XML: {sucesso} ok / {falha} falhas")

        # Lista os arquivos reais no diretório antes de compactar (debug)
        arquivos_xml = [f for f in os.listdir(download_dir) if f.endswith(".xml")]
        print(f"📂 Arquivos no diretório ({len(arquivos_xml)} XMLs): {arquivos_xml}")

        # Compacta em memória antes do finally limpar o diretório
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in arquivos_xml:
                caminho_completo = os.path.join(download_dir, f)
                zf.write(caminho_completo, f)
                print(f"  📄 Adicionado ao ZIP: {f} ({os.path.getsize(caminho_completo)} bytes)")
        zip_buffer.seek(0)

        # CORREÇÃO ZIP VAZIO: verifica pelo número de arquivos dentro do ZIP,
        # não pelo tamanho do buffer (que nunca é 0 mesmo com ZIP vazio).
        with zipfile.ZipFile(zip_buffer) as zf_check:
            arquivos_no_zip = zf_check.namelist()
        zip_buffer.seek(0)  # reposiciona após a verificação

        print(f"📦 Arquivos no ZIP: {arquivos_no_zip}")

        if not arquivos_no_zip:
            raise HTTPException(
                status_code=500,
                detail=f"Nenhum XML foi baixado com sucesso. "
                       f"Tentativas: {sucesso + falha}, Sucessos: {sucesso}. "
                       f"Verifique os logs do robô para mais detalhes."
            )

        nome_zip = f"xml_{req.cliente_id}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={nome_zip}"}
        )
    finally:
        if browser_tuple:
            await _fechar_browser(browser_tuple)
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)


# =========================
# ROTA: DOWNLOAD INDIVIDUAL — DANFSe (PDF oficial)
# O robô faz GET direto ao portal público via httpx (server-side).
# Sem CORS, sem autenticação necessária.
# CORREÇÃO: usa req.url_danfse (URL completa com data_chave encodado)
# em vez de montar a URL com chave_acesso (que é o número, não o token).
# =========================
@router.post("/baixar-danfse")
async def baixar_danfse_individual(req: DownloadRequest):
    # Usa url_danfse se disponível (já tem o data_chave encodado correto)
    # Fallback: monta com chave_acesso (pode não funcionar se não for o token)
    url = req.url_danfse or (
        f"https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave={req.chave_acesso}"
    )

    download_dir = f"/tmp/pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)
    caminho = os.path.join(download_dir, f"{req.chave_acesso}.pdf")

    try:
        if await _download_pdf_direto(url, caminho):
            return FileResponse(
                path=caminho,
                filename=f"{req.chave_acesso}.pdf",
                media_type="application/pdf"
            )
        raise HTTPException(status_code=500, detail="Portal não retornou PDF válido")
    finally:
        # Não remove aqui pois FileResponse ainda precisa ler o arquivo
        # O OS limpará /tmp automaticamente
        pass


# =========================
# ROTA: DOWNLOAD EM LOTE — DANFSe PDF (retorna ZIP)
# CORREÇÃO: usa nota.url_danfse (URL completa com token encodado)
# em vez de montar URL com chave_acesso numérica (que dava 404).
# O robô faz GET direto — sem CORS, sem autenticação.
# =========================
@router.post("/baixar-lote-danfse")
async def baixar_lote_danfse_route(req: DownloadLoteRequest):
    download_dir = f"/tmp/lote_pdf_{uuid.uuid4().hex}"
    os.makedirs(download_dir, exist_ok=True)

    try:
        sucesso, falha = 0, 0
        for nota in req.notas:
            chave = nota.chave_acesso or nota.data_chave or "nota"

            # CORREÇÃO: usa url_danfse completa (tem o data_chave encodado)
            # sem ela o portal retorna 404 pois a chave numérica não é o token
            url = nota.url_danfse
            if not url:
                print(f"⚠️ url_danfse ausente para {chave}, pulando")
                falha += 1
                continue

            caminho = os.path.join(download_dir, f"{chave}.pdf")
            ok = await _download_pdf_direto(url, caminho)
            if ok:
                sucesso += 1
            else:
                falha += 1

        print(f"✅ Lote DANFSe: {sucesso} ok / {falha} falhas")

        # Compacta em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in os.listdir(download_dir):
                if f.endswith(".pdf"):
                    zf.write(os.path.join(download_dir, f), f)
        zip_buffer.seek(0)

        if zip_buffer.getbuffer().nbytes == 0:
            raise HTTPException(status_code=500, detail="Nenhum DANFSe foi baixado com sucesso")

        nome_zip = f"danfse_{req.cliente_id}.zip"
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={nome_zip}"}
        )
    finally:
        if os.path.exists(download_dir):
            shutil.rmtree(download_dir, ignore_errors=True)


# =========================
# [NOVO v2] ROTA: IMPORTAR NOTAS VIA PORTAL MUNICIPAL (Atende.Net)
#
# Por que essa rota existe:
#   Os municípios de São José, Palhoça e Biguaçu não usam o Portal
#   Nacional (nfse.gov.br) nem certificado A1 para acesso do contribuinte.
#   Eles operam o sistema Atende.Net com login por usuário e senha.
#   Esta rota é exclusiva para esse fluxo — não substitui a rota
#   /importar-notas (certificado A1) que continua funcionando normalmente.
#
# Como funciona:
#   1. Valida se portal_url é um portal Atende.Net suportado
#   2. Valida se portal_usuario e portal_senha foram informados
#   3. Chama importar_via_atende() que faz scraping completo:
#      login → navegação → filtro de datas → extração de notas
#   4. Retorna a lista de notas encontradas em JSON
#
# Portais suportados nesta versão:
#   - São José/SC  → https://nfse-saojose.atende.net/...
#   - Palhoça/SC   → https://nfse-palhoca.atende.net/...
#   - Biguaçu/SC   → https://nfse-bigua.atende.net/...
#
# Como o Tributtus deve chamar esta rota:
#   POST /importar-notas-municipal com o body do ImportRequest
#   preenchendo portal_url, portal_usuario e portal_senha.
#   Se o cliente tiver certificado A1 → usa /importar-notas (original).
#   Se o cliente tiver credenciais de portal → usa esta rota.
# =========================
@router.post("/importar-notas-municipal")
async def importar_notas_municipal(req: ImportRequest):

    # [NOVO v2] Valida se a URL é de um portal Atende.Net suportado
    if not is_portal_atende(req.portal_url):
        raise HTTPException(
            status_code=400,
            detail=(
                f"portal_url inválida ou município não suportado: {req.portal_url}. "
                f"Portais aceitos: nfse-saojose, nfse-palhoca, nfse-bigua (.atende.net)"
            )
        )

    # [NOVO v2] Valida credenciais obrigatórias para portais municipais
    if not req.portal_usuario or not req.portal_senha:
        raise HTTPException(
            status_code=400,
            detail="portal_usuario e portal_senha são obrigatórios para portais municipais Atende.Net"
        )

    print(f"🏙️ [v2] Importação municipal iniciada")
    print(f"   Portal  : {req.portal_url}")
    print(f"   CNPJ    : {req.cnpj}")
    print(f"   Cliente : {req.cliente_id}")
    print(f"   Período : {req.data_inicio} → {req.data_fim}")

    try:
        # [NOVO v2] Chama o scraper do Atende.Net (atende_scraper.py)
        notas = await importar_via_atende(
            portal_url=req.portal_url,
            usuario=req.portal_usuario,
            senha=req.portal_senha,
            data_inicio=req.data_inicio,
            data_fim=req.data_fim,
        )

        print(f"✅ [v2] Importação municipal concluída: {len(notas)} nota(s) encontrada(s)")

        # [NOVO v2] Retorna no mesmo formato que o frontend espera
        return {
            "status": "concluido",
            "cliente_id": req.cliente_id,
            "cnpj": req.cnpj,
            "portal": req.portal_url,
            "data_inicio": req.data_inicio,
            "data_fim": req.data_fim,
            "notas_encontradas": len(notas),
            "notas": notas,
        }

    except HTTPException:
        raise  # repassa HTTPExceptions sem encapsular

    except Exception as e:
        print(f"❌ [v2] Erro na importação municipal: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro durante scraping do portal municipal: {str(e)}"
        )
