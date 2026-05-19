import tempfile
import os
import base64
from playwright.async_api import async_playwright
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption


async def criar_browser_com_certificado(certificado_base64: str, senha):
    print("🔐 Preparando certificado...")

    # 🔥 CORREÇÃO
    if not certificado_base64:
        raise Exception("Certificado não informado para criação do browser")

    # [NOVO CORREÇÃO] Remover prefixo data:...;base64, se presente.
    # O FileReader do browser pode enviar com esse prefixo — sem remover,
    # o base64.b64decode falha silenciosamente ou gera bytes corrompidos.
    if isinstance(certificado_base64, str) and "base64," in certificado_base64:
        certificado_base64 = certificado_base64.split("base64,")[1]
        print("⚠️  Prefixo data:base64 removido do certificado")

    # ================================
    # 1. DECODIFICA CERTIFICADO
    # ================================
    cert_bytes = base64.b64decode(certificado_base64)

    # [NOVO CORREÇÃO] Normalizar a senha para bytes antes de passar ao pkcs12.
    # A biblioteca cryptography exige bytes. Tratamos todos os casos possíveis:
    #   - str  → encode para bytes (caso normal vindo do JSON)
    #   - bytes → usar diretamente (já convertido em alguma camada anterior)
    #   - None  → usar bytes vazios b"" (certificado sem senha)
    if isinstance(senha, bytes):
        senha_bytes = senha
    elif isinstance(senha, str):
        senha_bytes = senha.encode("utf-8")
    else:
        senha_bytes = b""
        print("⚠️  Senha não informada — usando bytes vazios")

    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        cert_bytes,
        senha_bytes  # [NOVO CORREÇÃO] sempre bytes, nunca str ou None
    )

    # ================================
    # 2. CONVERTE PARA PEM
    # ================================
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption()
    )

    # ================================
    # 3. SALVA TEMPORÁRIOS
    # ================================
    fd_cert, cert_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_cert, 'wb') as tmp:
        tmp.write(cert_pem)

    fd_key, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd_key, 'wb') as tmp:
        tmp.write(key_pem)

    print(f"📄 Certificado salvo em: {cert_path}")
    print(f"🔑 Chave salva em: {key_path}")

    # ================================
    # 4. PLAYWRIGHT
    # ================================
    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-web-security",
            "--allow-running-insecure-content"
        ]
    )

    # ================================
    # 5. CONTEXTO COM CERTIFICADO
    # ================================
    context = await browser.new_context(
        viewport={'width': 1280, 'height': 800},

        # 🔥 CRÍTICO para ambientes cloud
        ignore_https_errors=True,

        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",

        # 🔥 CORREÇÃO PRINCIPAL (multi-origin)
        client_certificates=[
            {
                "origin": "https://www.nfse.gov.br",
                "certPath": cert_path,
                "keyPath": key_path
            },
            {
                "origin": "https://nfse.gov.br",
                "certPath": cert_path,
                "keyPath": key_path
            }
        ]
    )

    # ================================
    # 6. PAGE
    # ================================
    page = await context.new_page()

    page.set_default_timeout(60000)

    print("🌐 Browser pronto com certificado!")

    return p, browser, context, page, cert_path, key_path
