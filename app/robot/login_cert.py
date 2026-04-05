def login_certificado(page):
    try:
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional",
            wait_until="networkidle"
        )
        page.wait_for_timeout(2000)

        # Clica em "Acesso com certificado digital"
        page.click("text=Acesso com certificado digital")
        page.wait_for_timeout(3000)

        # Aguarda redirecionar para o painel
        page.wait_for_url("**/EmissorNacional**", timeout=30000)
        
        print("Login com certificado realizado com sucesso!")
        return True

    except Exception as e:
        raise Exception(f"Falha no login com certificado: {str(e)}")
