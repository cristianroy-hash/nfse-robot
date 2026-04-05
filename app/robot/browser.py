import tempfile
import os
import base64
from playwright.sync_api import sync_playwright

def criar_browser_com_certificado(certificado_base64: str, senha: str):
    # 1. Decodifica e salva o PFX original em um arquivo temporário
    # O Playwright 1.46+ prefere lidar diretamente com o PFX para mTLS
    cert_bytes = base64.b64decode(certificado_base64)
    
    # Criamos o arquivo temporário .pfx
    fd, pfx_path = tempfile.mkstemp(suffix=".pfx")
    try:
        with os.fdopen(fd, 'wb') as tmp:
            tmp.write(cert_bytes)
    except Exception as e:
        os.close(fd)
        raise Exception(f"Falha ao salvar certificado temporário: {str(e)}")

    # 2. Inicia o Playwright
    p = sync_playwright().start()
    
    # Argumentos otimizados para rodar em containers (Railway)
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--ignore-certificate-errors" # Ajuda em portais governamentais com cadeias de cert incompletas
        ]
    )

    # 3. Cria o contexto usando 'pfxPath' em vez de separar cert/key
    # Isso é muito mais robusto no Linux
    context = browser.new_context(
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "pfxPath": pfx_path,
            "password": senha
        }]
    )

    page = context.new_page()
    page.set_default_timeout(60000)
    
    # Retornamos pfx_path duas vezes para manter compatibilidade com o 
    # desempacotamento (cert_path, key_path) no seu import_service.py
    return p, browser, context, page, pfx_path, pfx_path
