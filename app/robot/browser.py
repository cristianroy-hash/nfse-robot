import tempfile
import os
import base64
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

def criar_browser_com_certificado(certificado_base64: str, senha: str):
    # 1. Decodifica o certificado
    cert_bytes = base64.b64decode(certificado_base64)
    
    # 2. Extrai a chave e o certificado
    # O PKCS12 extrai os componentes para que o Playwright use via certPath/keyPath
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        cert_bytes, senha.encode()
    )
    
    # 3. Converte para PEM (Formato que o Playwright aceita via arquivo)
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    
    # 4. Salva em arquivos temporários (serão deletados no finally do import_service)
    fd_cert, cert_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_cert, 'wb') as tmp:
        tmp.write(cert_pem)
        
    fd_key, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_key, 'wb') as tmp:
        tmp.write(key_pem)

    # 5. Inicia o Playwright
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", 
            "--disable-setuid-sandbox", 
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled" # Ajuda a evitar detecção de robô
        ]
    )

    # 6. Cria o contexto com Certificado e Configurações de Tela
    context = browser.new_context(
        # Define um tamanho de tela de computador para os campos não sumirem
        viewport={'width': 1280, 'height': 800},
        # Simula um navegador real para evitar bloqueios do portal
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "certPath": cert_path,
            "keyPath": key_path
        }]
    )

    page = context.new_page()
    page.set_default_timeout(60000)
    
    return p, browser, context, page, cert_path, key_path
