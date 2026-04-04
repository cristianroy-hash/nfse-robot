import base64
import tempfile
import os

def login_certificado(page, context, certificado_base64: str, certificado_senha: str):
    # Salva o certificado temporariamente
    cert_bytes = base64.b64decode(certificado_base64)
    
    with tempfile.NamedTemporaryFile(suffix=".pfx", delete=False) as tmp:
        tmp.write(cert_bytes)
        cert_path = tmp.name

    try:
        # Acessa o portal nacional NFS-e
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login", wait_until="networkidle")

        # Clica na opção de certificado digital
        page.click("text=Certificado Digital")

        # Aguarda carregar
        page.wait_for_timeout(2000)

        # Retorna o caminho do certificado para uso externo
        return cert_path

    except Exception as e:
        raise Exception(f"Falha no login com certificado: {str(e)}")
    
    finally:
        # Remove o arquivo temporário
        if os.path.exists(cert_path):
            os.remove(cert_path)
