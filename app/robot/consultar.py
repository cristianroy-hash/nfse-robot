import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"--- INICIANDO CAPTURA VIA PERÍODO ---")
        
        # Caminho 1: Tenta ir direto
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="load")
        
        # ESPERA ATIVA: Em vez de wait_for_selector direto, vamos tentar um loop de 3 tentativas
        campo_visivel = False
        for i in range(3):
            try:
                print(f"Tentativa {i+1} de localizar campos de data...")
                page.wait_for_selector("input[name*='DataEmissao']", timeout=7000)
                campo_visivel = True
                break
            except:
                # Caminho 2: Se não carregou, tenta clicar no menu 'Consultar' que costuma estar no topo
                print("Campo não visível. Tentando clicar no menu Consultar...")
                page.locator("a:has-text('Consultar')").first.click(force=True)
                page.wait_for_timeout(3000)

        if not campo_visivel:
            # Caminho 3: Fallback final via JS
            print("Forçando navegação via JavaScript...")
            page.evaluate("window.location.href='/EmissorNacional/NFSes/Emitidas'")
            page.wait_for_selector("input[name*='DataEmissaoInicio']", timeout=15000)

        # ... restante do código de preenchimento (use o page.type com delay que mandei antes)

        # 4. Preenchimento "Lento" (Simulando humano para o site não travar)
        page.locator("input[name*='DataEmissaoInicio']").click()
        page.locator("input[name*='DataEmissaoInicio']").fill("")
        page.type("input[name*='DataEmissaoInicio']", data_inicio, delay=100)
        
        page.locator("input[name*='DataEmissaoFim']").click()
        page.locator("input[name*='DataEmissaoFim']").fill("")
        page.type("input[name*='DataEmissaoFim']", data_fim, delay=100)

        # 5. Clique no botão Filtrar/Consultar
        # O botão principal de consulta costuma ter a classe btn-primary
        page.click("button:has-text('Consultar'), button.btn-primary")
        
        print("-> Filtro aplicado, aguardando resultados...")
        page.wait_for_timeout(5000) # Tempo para o grid atualizar

        # 6. Captura das notas
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
        # Tira um print do erro para debug se necessário
        page.screenshot(path="erro_consulta.png")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    capturado = {"id": None}

    def check_network(response):
        # Escuta URLs que contenham o padrão de download de XML
        if "Download/NFSe" in response.url:
            match = re.search(r'/([0-9]{40,60})', response.url)
            if match:
                capturado["id"] = match.group(1)

    try:
        idx = nota["index"]
        page.on("response", check_network)
        
        print(f"-> Processando nota {idx}...")
        
        # 1. Tenta extrair o ID que já veio no HTML (estratégia mais rápida)
        id_match = re.search(r'Download/NFSe/([0-9]{40,60})', nota.get('html', ''))
        if id_match:
            capturado["id"] = id_match.group(1)
            print(f"   [INFO] ID extraído diretamente da linha.")

        # 2. Se não achou, clica na linha para forçar o carregamento do link/popover
        if not capturado["id"]:
            linha = page.locator("table tbody tr").nth(idx)
            linha.click()
            page.wait_for_timeout(2000)
            
            # Tenta buscar o link no corpo da página após o clique
            capturado["id"] = page.evaluate("""() => {
                const match = document.body.innerHTML.match(/Download\/NFSe\/([0-9]{40,60})/);
                return match ? match[1] : null;
            }""")

        if capturado["id"]:
            id_nota = capturado["id"]
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/{id_nota}"
            print(f"   [ALVO] Link identificado: ...{id_nota[-10:]}")
            
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")
            
            # Realiza o download via URL direta para evitar cliques errados em popovers
            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML salvo!")
            page.remove_listener("response", check_network)
            return True
        else:
            print(f"   [ERRO] Não foi possível obter o identificador da nota {idx}.")
            page.remove_listener("response", check_network)
            return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        return False
