import traceback

def login_certificado(page):
    try:
        print("Acessando portal NFS-e...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login", wait_until="networkidle")
        
        # 1. Clica no botão de certificado
        print("Clicando no botão de Certificado Digital...")
        botao_cert = page.locator("a.btn-login-certificado, text='Certificado Digital'").first
        botao_cert.click()
        
        # 2. Aguarda um momento para o handshake mTLS ocorrer
        page.wait_for_timeout(5000)
        
        # 3. FORÇA a entrada na home logada
        # Muitas vezes o portal autentica mas o JS de redirecionamento falha no modo headless
        print("Forçando navegação para área logada...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/", wait_until="networkidle")
        
        # 4. Verifica se agora estamos logados (procurando botão Sair ou similar)
        url_final = page.url
        print(f"URL após tentativa de entrada: {url_final}")
        
        if "Login" in url_final:
            # Tentativa final: ir direto para a página de consulta que você quer
            print("Ainda no login. Tentativa final de bypass direto...")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
            page.wait_for_timeout(3000)
            
        if "Login" in page.url:
             raise Exception("Portal insiste na tela de login mesmo após envio do certificado.")
             
        print("Login confirmado via bypass de URL!")

    except Exception as e:
        page.screenshot(path="/tmp/erro_login.png")
        print(f"Erro no login: {traceback.format_exc()}")
        raise Exception(f"Falha no login: {str(e)}")
