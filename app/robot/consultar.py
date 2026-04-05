import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"--- INICIANDO CAPTURA VIA PERÍODO ---")
        print(f"Período: {data_inicio} a {data_fim}")

        # DIAGNÓSTICO — ver onde estamos ANTES de navegar
        url_antes = page.url
        links_antes = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a, button'))
                .map(el => ({
                    text: el.innerText.trim().substring(0, 60),
                    href: el.href || '',
                    class: el.className || ''
                }))
                .filter(el => el.text);
        }""")
        print(f"URL antes de navegar: {url_antes}")
        print(f"Links disponíveis antes: {links_antes}")

        # Navega para a página de notas emitidas
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas",
            wait_until="load"
        )
        page.wait_for_timeout(5000)

        # DIAGNÓSTICO — ver o que carregou após navegação
        url_depois = page.url
        print(f"URL após navegação: {url_depois}")

        dados_pagina = page.evaluate("""() => {
            return {
                titulo: document.title,
                texto: document.body.innerText.substring(0, 1000),
                inputs: Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id,
                    name: i.name,
                    type: i.type,
                    class: i.className,
                    placeholder: i.placeholder
                })),
                links: Array.from(document.querySelectorAll('a')).map(a => ({
                    text: a.innerText.trim().substring(0, 50),
                    href: a.href
                })).filter(a => a.text),
                iframes: Array.from(document.querySelectorAll('iframe')).map(f => ({
                    src: f.src, id: f.id, name: f.name
                }))
            }
        }""")

        print(f"Título: {dados_pagina['titulo']}")
        print(f"Texto: {dados_pagina['texto']}")
        print(f"Inputs: {dados_pagina['inputs']}")
        print(f"Links: {dados_pagina['links']}")
        print(f"Iframes: {dados_pagina['iframes']}")

        # ESPERA ATIVA pelos campos de data
        campo_visivel = False
        for i in range(3):
            try:
                print(f"Tentativa {i+1} de localizar campos de data...")
                page.wait_for_selector("input[name*='DataEmissao']", timeout=7000)
                campo_visivel = True
                print("Campo de data encontrado!")
                break
            except:
                print("Campo não visível. Tentando clicar no menu Consultar...")
                try:
                    page.locator("a:has-text('Consultar')").first.click(force=True)
                    page.wait_for_timeout(3000)
                except:
                    print("Menu Consultar também não encontrado.")

        if not campo_visivel:
            print("Forçando navegação via JavaScript...")
            page.evaluate("window.location.href='/EmissorNacional/NFSes/Emitidas'")
            try:
                page.wait_for_selector("input[name*='DataEmissaoInicio']", timeout=15000)
                campo_visivel = True
            except:
                print("Campos de data não encontrados mesmo após forçar navegação.")

        if not campo_visivel:
            print("Capturando HTML completo para diagnóstico final...")
            html = page.content()
            print(f"HTML completo (5000 chars): {html[:5000]}")
            return []

        # Preenchimento das datas
        print("Preenchendo campos de data...")
        page.locator("input[name*='DataEmissaoInicio']").click()
        page.locator("input[name*='DataEmissaoInicio']").fill("")
        page.type("input[name*='DataEmissaoInicio']", data_inicio, delay=100)

        page.locator("input[name*='DataEmissaoFim']").click()
        page.locator("input[name*='DataEmissaoFim']").fill("")
        page.type("input[name*='DataEmissaoFim']", data_fim, delay=100)

        # Clique no botão Filtrar
        print("Clicando em Filtrar...")
        page.click("button:has-text('Consultar'), button:has-text('Filtrar'), button.btn-primary")
        page.wait_for_timeout(5000)

        # Captura das notas
        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => ({
                index: i,
                texto: row.innerText,
                html: row.innerHTML
            })).filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'));
        }""")

        print(f"Notas detectadas: {len(notas)}")
        return notas

    except Exception as e:
        print(f"Erro na consulta: {str(e)}")
        page.screenshot(path="/tmp/erro_consulta.png")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    capturado = {"id": None}

    def check_network(response):
        if "Download/NFSe" in response.url:
            match = re.search(r'/([0-9]{40,60})', response.url)
            if match:
                capturado["id"] = match.group(1)

    try:
        idx = nota["index"]
        page.on("response", check_network)
        print(f"-> Processando nota {idx}...")

        # Tenta extrair o ID direto do HTML da linha
        id_match = re.search(r'Download/NFSe/([0-9]{40,60})', nota.get('html', ''))
        if id_match:
            capturado["id"] = id_match.group(1)
            print(f"   ID extraído diretamente da linha.")

        # Se não achou, clica na linha para forçar carregamento
        if not capturado["id"]:
            linha = page.locator("table tbody tr").nth(idx)
            linha.click()
            page.wait_for_timeout(2000)
            capturado["id"] = page.evaluate("""() => {
                const match = document.body.innerHTML.match(/Download\/NFSe\/([0-9]{40,60})/);
                return match ? match[1] : null;
            }""")

        if capturado["id"]:
            id_nota = capturado["id"]
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/{id_nota}"
            print(f"   Link identificado: ...{id_nota[-10:]}")

            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)

            download_info.value.save_as(caminho_local)
            print(f"   XML salvo!")
            page.remove_listener("response", check_network)
            return True
        else:
            print(f"   Não foi possível obter o ID da nota {idx}.")
            page.remove_listener("response", check_network)
            return False

    except Exception as e:
        print(f"   Falha: {e}")
        return False
