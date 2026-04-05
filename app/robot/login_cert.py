import traceback

def login_certificado(page):
    try:
        print("Acessando portal NFS-e...")
        # Aumentamos o timeout para o portal processar o certificado na entrada
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login", wait_until="domcontentloaded", timeout=60000)
        
        # 1. Clica no botão de certificado (Sintaxe corrigida)
        print("Clicando no botão de Certificado Digital...")
        # Usamos seletores separados para evitar erro de parsing
        botao_cert = page.locator("a.btn-login-certificado").first or \
                     page.get_by_text("Certificado Digital").first or \
                     page.locator("text=Certificado Digital").first
        
        botao_cert.click(timeout=15000)
        
        # 2. Aguarda o handshake mTLS
        print("Aguardando processamento do certificado...")
        page.wait_for_timeout(5000)
        
        # 3. BYPASS: Força a entrada na área logada
        # Como o certificado já foi enviado, o servidor deve reconhecer a sessão aqui
        print("Forçando navegação para a home logada...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/", wait_until="networkidle", timeout=60000)
        
        # 4. Verificação de sucesso
        url_final = page.url
        print(f"URL atual: {url_final}")
        
        # Se ainda estiver na tela de login, tenta ir direto para a consulta de notas
        if "Login" in url_final:
            print("Ainda detectado na tela de login. Tentando acesso direto à consulta...")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle")
            page.wait_for_timeout(3000)

        # Se o botão "Sair" ou "Emitir" existir, estamos dentro!
        if "Login" in page.url and not page.locator("text=Sair").is_visible():
             raise Exception("O portal não autorizou o acesso. Verifique se o certificado é válido para o Portal Nacional.")
             
        print("Login confirmado com sucesso!")

    except Exception as e:
        page.screenshot(path="/tmp/erro_login_final.png")
        print(f"Erro detalhado no login: {traceback.format_exc()}")
        raise Exception(f"Falha no login: {str(e)}")
