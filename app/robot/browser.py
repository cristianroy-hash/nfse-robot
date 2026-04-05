import tempfile
import os
import base64
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

def criar_browser_com_certificado(certificado_base64: str, senha: str):
    # Decodifica o certificado
    cert_bytes = base64.b64decode(certificado_base64)
    
    # Extrai a chave e o certificado usando a biblioteca cryptography (mais robusto que o motor interno do Chromium para mTLS)
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        cert_bytes, senha.encode()
    )
    
    # Converte para PEM
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    
    # Salva em arquivos temporários
    fd_cert, cert_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_cert, 'wb') as tmp:
        tmp.write(cert_pem)
        
    fd_key, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_key, 'wb') as tmp:
        tmp.write(key_pem)

    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )

    # USANDO certPath e keyPath (resolve o mac verify failure)
    context = browser.new_context(
    client_certificates=[{
        "origin": "https://www.nfse.gov.br", # O Playwright aplicará a todos os caminhos desta origem
        "certPath": cert_path,
        "keyPath": key_path
        }]
    )

    page = context.new_page()
    page.set_default_timeout(60000)
    
    return p, browser, context, page, cert_path, key_path
