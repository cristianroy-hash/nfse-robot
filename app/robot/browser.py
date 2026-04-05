import tempfile
import os
import base64
# MUDANÇA: Usamos async_api agora
from playwright.async_api import async_playwright
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

# MUDANÇA: A função agora é 'async def'
async def criar_browser_com_certificado(certificado_base64: str, senha: str):
    # 1. Decodifica o certificado
    cert_bytes = base64.b64decode(certificado_base64)
    
    # 2. Extrai a chave e o certificado (Esta parte continua síncrona, sem problemas)
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        cert_bytes, senha.encode()
    )
    
    # 3. Converte para PEM
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    
    # 4. Salva em arquivos temporários
    fd_cert, cert_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_cert, 'wb') as tmp:
        tmp.write(cert_pem)
        
    fd_key, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_key, 'wb') as tmp:
        tmp.write(key_pem)

    # 5. Inicia o Playwright de forma ASSÍNCRONA
    # MUDANÇA: Usamos 'await' em todos os comandos do Playwright
    p = await async_playwright().start()
    
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled"
        ]
    )

    # 6. Cria o contexto com Certificado (MUDANÇA: Adicionado await)
    context = await browser.new_context(
        viewport={'width': 1280, 'height': 800},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "certPath": cert_path,
            "keyPath": key_path
        }]
    )

    page = await context.new_page()
    page.set_default_timeout(60000)
    
    return p, browser, context, page, cert_path, key_path
