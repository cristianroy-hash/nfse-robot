import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"--- INICIANDO CAPTURA VIA PERÍODO ---")
        
        # 1. Em vez de ir direto pela URL, vamos interagir com o menu
        # Isso garante que os scripts da página sejam carregados na ordem certa
        print("-> Acessando menu de consulta...")
        
        # Tenta clicar no menu 'Notas Fiscais' e depois 'Emitidas'
        # Se os seletores mudarem, o goto ainda está aqui como fallback, mas com mais espera
        try:
            # Tenta clicar no ícone de lupa ou menu de consulta se estiver visível
            if page.locator("a:has-text('Consultar')").is_visible():
                page.click("a:has-text('Consultar')")
            else:
                page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle")
        except:
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")

        # 2. ESPERA CRUCIAL: Aguarda o formulário de filtros carregar
        # Aumentamos para 30s pois o portal do governo oscila muito
        page.wait_for_selector("input[name*='DataEmissaoInicio']", timeout=30000)
        print("-> Campos de consulta localizados.")

        # 3. Conversão de data (HTML AAAA-MM-DD para Portal DD/MM/AAAA)
        if '-' in data_inicio:
            ano_i, mes_i, dia_i = data_inicio.split('-')
            data_inicio = f"{dia_i}/{mes_i}/{ano_i}"
        if '-' in data_fim:
            ano_f, mes_f, dia_f = data_fim.split('-')
            data_fim = f"{dia_f}/{mes_f}/{ano_f}"

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
