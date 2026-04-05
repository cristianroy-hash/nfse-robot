import traceback

def login_certificado(page):
    try:
        print("Acessando portal NFS-e...")
        # Aumentamos o timeout global e aguardamos o carregamento inicial
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login", wait_until="domcontentloaded", timeout=90000)
        
        # 1. Busca exaustiva pelo botão de certificado
        print("Localizando botão de acesso por certificado...")
        
        # Tentamos por texto, que é o mais garantido visualmente
        # Buscamos 'Certificado Digital' ou 'Entrar com Certificado'
        botao_cert = page.get_by_text("Certificado Digital", exact=False).first
        
        # Se não estiver visível, tentamos por seletores de classe comuns do portal
        if not botao_cert.is_visible():
            botao_cert = page.locator("a.btn-login-certificado").first or \
                         page.locator(".autenticacao button").first or \
                         page.locator("a:has-text('Certificado')").first

        # Aguarda o botão ficar pronto para clique
        botao_cert.wait_for(state="visible", timeout=30000)
        print("Botão encontrado. Clicando...")
        botao_cert.click()
        
        # 2. Pequena pausa para o handshake mTLS (envio do PEM)
        page.wait_for_timeout(5000)
        
        # 3. BYPASS de Redirecionamento: Força a URL interna
        # Se o certificado foi aceito, navegar para a home logada confirmará a sessão
        print("Forçando entrada na área restrita...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/", wait_until="networkidle", timeout=60000)
        
        # 4. Verificação de Sucesso
        url_atual = page.url
        print(f"URL alcançada: {url_atual}")
        
        # Se ainda estiver na URL de login, tentamos o pulo direto para emissão/consulta
        if "Login" in url_atual:
            print("Ainda na tela de login. Tentando salto direto para Notas Emitidas...")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

        # O teste final é ver se o link de "Sair" ou o perfil do contribuinte aparece
        if "Login" in page.url:
             # Tira print para debug no Railway
             page.screenshot(path="/tmp/falha_login_pos_clique.png")
             raise Exception("O portal não autorizou o acesso após o envio do certificado PEM.")
             
        print("Login confirmado com sucesso!")

    except Exception as e:
        page.screenshot(path="/tmp/erro_login_fatal.png")
        print(f"Detalhes do erro: {traceback.format_exc()}")
        raise Exception(f"Falha no login: {str(e)}")
