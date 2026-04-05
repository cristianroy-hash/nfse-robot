import tempfile
import os
import base64
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

def pfx_para_pem(certificado_base64: str, senha: str):
    cert_bytes = base64.b64decode(certificado_base64)
    
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        cert_bytes, senha.encode()
    )
    
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    
    cert_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    cert_file.write(cert_pem)
    cert_file.close()
    
    key_file = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    key_file.write(key_pem)
    key_file.close()
    
    return cert_file.name, key_file.name

def criar_browser_com_certificado(certificado_base64: str, senha: str):
    cert_path, key_path = pfx_para_pem(certificado_base64, senha)
    
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "certPath": cert_path,
            "keyPath": key_path,
            "passphrase": senha
        }]
    )
    page = context.new_page()
    page.set_default_timeout(60000)
    
    return p, browser, context, page, cert_path, key_path
