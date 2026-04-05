import traceback

def login_certificado(page):
    try:
        print("Acessando portal NFS-e...")
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Login",
            wait_until="domcontentloaded",
            timeout=90000
        )
        page.wait_for_timeout(3000)

        # Captura o href exato do botão de certificado
        href = page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a'));
            const cert = links.find(l => l.innerText.toLowerCase().includes('certificado'));
            return cert ? { href: cert.href, text: cert.innerText.trim() } : null;
        }""")
        print(f"Link certificado capturado: {href}")

        # Clica no botão
        print("Clicando no botão 'Certificado Digital'...")
        botao = page.get_by_text("Certificado Digital", exact=False).first
        botao.wait_for(state="visible", timeout=30000)
        botao.click()
        
        # Aguarda o handshake mTLS (importante para o PEM ser enviado)
        page.wait_for_timeout(5000)
        print(f"URL após clique: {page.url}")

        # Se ainda estiver no login, navega direto pelo href capturado
        if "Login" in page.url and href and href.get("href"):
            print(f"Tentando navegar direto para o endpoint de autenticação: {href['href']}")
            page.goto(href["href"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)

        # Tenta ir para a home autenticada (Salto de Segurança)
        print("Validando sessão na Home...")
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Verificação de elementos de usuário logado
        logado = page.evaluate("""() => {
            const body = document.body.innerText.toLowerCase();
            return {
                tem_sair: body.includes('sair'),
                tem_logout: body.includes('logout'),
                tem_emitir: body.includes('emitir'),
                tem_consultar: body.includes('consultar'),
                tem_contribuinte: body.includes('contribuinte')
            }
        }""")
        
        print(f"Verificação de login: {logado}")

        if logado["tem_sair"] or logado["tem_emitir"] or logado["tem_consultar"]:
            print("Login confirmado com sucesso!")
            return True

        # Se falhou, tira print para debug
        page.screenshot(path="/tmp/falha_login_detalhada.png")
        raise Exception(f"Portal não autorizou acesso. URL final: {page.url}")

    except Exception as e:
        print(f"Detalhes do erro no login: {traceback.format_exc()}")
        raise Exception(f"Falha no login: {str(e)}")
