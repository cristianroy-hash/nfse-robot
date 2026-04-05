def login_certificado(page):
    try:
        print("Acessando portal NFS-e com certificado...")
        
        # Tenta acessar direto o painel — se o certificado for aceito 
        # automaticamente via mTLS, não precisa clicar em nada
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Certificado",
            wait_until="domcontentloaded",
            timeout=60000
        )
        page.wait_for_timeout(4000)
        
        url_atual = page.url
        titulo = page.title()
        html = page.content()
        print(f"URL: {url_atual}")
        print(f"Título: {titulo}")
        print(f"HTML (2000 chars): {html[:2000]}")

        # Se foi redirecionado para login, tenta clicar no botão
        if "Login" in url_atual:
            print("Redirecionou para login, tentando clicar no botão...")
            
            # Aguarda um pouco mais para a página carregar completamente
            page.wait_for_timeout(3000)
            
            # Tira screenshot para debug
            page.screenshot(path="/tmp/login_page.png")
            print("Screenshot salvo em /tmp/login_page.png")
            
            el = page.query_selector("text=Acesso com certificado digital")
            if el:
                el.click()
                page.wait_for_timeout(8000)
                print(f"URL após clique: {page.url}")
                html2 = page.content()
                print(f"HTML após clique (2000 chars): {html2[:2000]}")
            else:
                print("Botão não encontrado — HTML da página:")
                print(html[:3000])

        # Verifica se está logado
        url_final = page.url
        print(f"URL final: {url_final}")
        
        if "Login" not in url_final and "EmissorNacional" in url_final:
            print("Login realizado com sucesso!")
            return True
        
        # Verifica se tem elementos do painel na página
        painel = page.query_selector("text=Emitir NFS-e") or \
                 page.query_selector("text=Consultar NFS-e") or \
                 page.query_selector("text=Sair") or \
                 page.query_selector("text=Logout")
        
        if painel:
            print("Painel encontrado — login OK!")
            return True

        raise Exception(f"Não foi possível confirmar o login. URL final: {url_final}")

    except Exception as e:
        raise Exception(f"Falha no login com certificado: {str(e)}")
