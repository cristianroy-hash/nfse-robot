import traceback

async def login_certificado(page):
    try:
        print("Tentando autenticação direta pelo endpoint de certificado...")
        
        # O goto agora precisa de await
        await page.goto("https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional", wait_until="networkidle")
        
        # O wait_for_timeout agora precisa de await
        await page.wait_for_timeout(5000)

        # O evaluate agora precisa de await
        diagnostico = await page.evaluate('''() => {
            return {
                url: window.location.href,
                tem_contribuinte: document.body.innerText.includes("Contribuinte"),
                tem_sair: document.body.innerText.includes("Sair")
            };
        }''')

        print(f"URL alcançada: {diagnostico['url']}")

        # Agora o 'diagnostico' é um dicionário real, não uma corrotina
        if diagnostico["tem_contribuinte"] or diagnostico["tem_sair"]:
            print("Autenticação realizada com sucesso!")
            return True
        else:
            # Se não logou direto, tenta clicar no botão de certificado se existir
            print("Não detectado login automático, tentando clicar no botão...")
            await page.click("text=Certificado Digital") # Exemplo de seletor
            await page.wait_for_timeout(5000)
            return True

    except Exception as e:
        print(f"Erro detalhado no Login: {traceback.format_exc()}")
        raise Exception(f"Falha no processo de autenticação: {str(e)}")
