import tempfile
import os
import base64
from playwright.sync_api import sync_playwright
from OpenSSL import crypto

def pfx_para_pem(certificado_base64: str, senha: str):
    cert_bytes = base64.b64decode(certificado_base64)
    pfx = crypto.load_pkcs12(cert_bytes, senha.encode())
    
    cert_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, pfx.get_certificate())
    key_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, pfx.get_privatekey())
    
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
