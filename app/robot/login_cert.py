def login_certificado(page):
    try:
        print("Acessando portal NFS-e...")
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional",
            wait_until="domcontentloaded",
            timeout=60000
        )
        page.wait_for_timeout(3000)
        print(f"URL atual: {page.url}")
        print(f"Título da página: {page.title()}")

        # Tenta diferentes seletores para o botão de certificado
        seletores = [
            "text=Acesso com certificado digital",
            "text=Certificado Digital",
            "text=certificado",
            "a[href*='certificado']",
            "button[class*='certificado']",
            "input[type='submit'][value*='ertificado']"
        ]

        clicou = False
        for seletor in seletores:
            try:
                el = page.query_selector(seletor)
                if el:
                    print(f"Botão encontrado com seletor: {seletor}")
                    el.click()
                    clicou = True
                    break
            except:
                continue

        if not clicou:
            # Captura o HTML da página para debugar
            html = page.content()
            print(f"HTML da página (primeiros 2000 chars): {html[:2000]}")
            raise Exception("Botão de certificado digital não encontrado na página")

        print("Botão clicado, aguardando redirecionamento...")
        page.wait_for_timeout(5000)
        print(f"URL após clique: {page.url}")

        # Verifica se já está logado
        if "EmissorNacional" in page.url and "Login" not in page.url:
            print("Login realizado com sucesso!")
            return True

        # Aguarda mais tempo para o redirecionamento
        page.wait_for_url("**/EmissorNacional**", timeout=60000)
        print("Login com certificado realizado com sucesso!")
        return True

    except Exception as e:
        raise Exception(f"Falha no login com certificado: {str(e)}")
