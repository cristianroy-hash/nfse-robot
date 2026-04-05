import traceback

def login_certificado(page):
    try:
        print("Tentando autenticação direta pelo endpoint de certificado...")
        
        # 1. Tenta o 'tiro direto' no endpoint de certificado
        # O Playwright enviará o certificado PEM automaticamente
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Certificado",
            wait_until="networkidle",
            timeout=90000
        )
        
        # Espera o portal processar o redirecionamento inicial
        page.wait_for_timeout(5000)
        url_atual = page.url
        print(f"URL alcançada: {url_atual}")
        
        # 2. Scanner de diagnóstico para entender onde o robô caiu
        diagnostico = page.evaluate("""() => {
            const body = document.body.innerText.toLowerCase();
            return {
                tem_sair: body.includes('sair'),
                tem_emitir: body.includes('emitir'),
                tem_consultar: body.includes('consultar'),
                tem_contribuinte: body.includes('contribuinte'),
                html_preview: body.substring(0, 300)
            }
        }""")
        
        print(f"Diagnóstico da página: {diagnostico}")

        # 3. Lógica de Seleção de Perfil (O ponto onde estava travando)
        if "Login" not in url_atual:
            # Se encontrou o botão 'Contribuinte', precisamos clicar e ESPERAR a sessão mudar
            if diagnostico["tem_contribuinte"] and not diagnostico["tem_sair"]:
                print("Perfil de Contribuinte detectado. Iniciando troca de perfil...")
                
                # Tenta clicar no botão de perfil
                botao_perfil = page.get_by_text("Contribuinte", exact=False).first
                botao_perfil.click()
                
                # Aguarda o portal recarregar a sessão (essencial para o governo)
                page.wait_for_timeout(6000)
                
                # Verificação de segurança: se o botão ainda estiver lá, clica de novo (forçado)
                if page.get_by_text("Contribuinte", exact=False).first.is_visible():
                    print("Botão ainda visível. Tentando clique forçado...")
                    page.get_by_text("Contribuinte", exact=False).first.click(force=True)
                    page.wait_for_timeout(4000)

            print("Login confirmado e perfil selecionado!")
            return True

        # 4. Caso o acesso direto falhe, tenta o fluxo manual via botão da tela de Login
        print("Acesso direto não confirmou login. Tentando fallback via botão...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login")
        
        btn_cert = page.get_by_text("Certificado Digital", exact=False).first
        if btn_cert.is_visible():
            btn_cert.click()
            page.wait_for_timeout(8000)
            
            # Repete a lógica de perfil se necessário no fallback
            if "Contribuinte" in page.content():
                page.get_by_text("Contribuinte", exact=False).first.click()
                page.wait_for_timeout(5000)
            
            if "Login" not in page.url:
                print("Login bem-sucedido via fallback!")
                return True

        # Se chegar aqui, algo deu errado
        page.screenshot(path="falha_login.png")
        raise Exception(f"Não foi possível estabelecer sessão. URL atual: {page.url}")

    except Exception as e:
        print(f"Erro detalhado no Login: {traceback.format_exc()}")
        raise Exception(f"Falha no processo de autenticação: {str(e)}")
