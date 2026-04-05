import traceback

def login_certificado(page):
    try:
        print("Tentando autenticação direta pelo endpoint de certificado...")
        
        # 1. Tenta o 'tiro direto' no endpoint de certificado
        # O Playwright enviará o PEM automaticamente aqui
        response = page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Certificado",
            wait_until="networkidle",
            timeout=90000
        )
        
        page.wait_for_timeout(5000)
        url_atual = page.url
        print(f"URL alcançada: {url_atual}")
        
        # 2. Scanner de diagnóstico (Sua lógica de verificação)
        logado = page.evaluate("""() => {
            const body = document.body.innerText.toLowerCase();
            return {
                tem_sair: body.includes('sair'),
                tem_emitir: body.includes('emitir'),
                tem_consultar: body.includes('consultar'),
                tem_contribuinte: body.includes('contribuinte'),
                html_preview: body.substring(0, 300)
            }
        }""")
        
        print(f"Diagnóstico da página: {logado}")

        # 3. Lógica de decisão
        # Se redirecionou para fora do Login ou se encontrou palavras-chave de sucesso
        if "Login" not in url_atual and (logado["tem_sair"] or logado["tem_emitir"] or logado["tem_contribuinte"]):
            print("Login confirmado via acesso direto ao endpoint!")
            
            # Se cair na tela de 'Contribuinte' (seleção de perfil), dá o clique final
            if logado["tem_contribuinte"] and not logado["tem_sair"]:
                print("Clicando no perfil de Contribuinte para finalizar...")
                page.get_by_text("Contribuinte", exact=False).first.click()
                page.wait_for_timeout(3000)
                
            return True

        # 4. Caso o tiro direto falhe, ele tenta o fluxo normal (Fallback)
        print("Acesso direto não confirmou login. Tentando fluxo via tela de Login...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/Login")
        page.get_by_text("Certificado Digital", exact=False).first.click()
        page.wait_for_timeout(7000)
        
        if "Login" not in page.url:
            print("Login bem-sucedido via clique no botão!")
            return True

        page.screenshot(path="/tmp/falha_final_login.png")
        raise Exception(f"Certificado recusado ou sessão não iniciada. URL: {page.url}")

    except Exception as e:
        print(f"Erro detalhado: {traceback.format_exc()}")
        raise Exception(f"Falha no login: {str(e)}")
