import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"--- INICIANDO CAPTURA VIA PERÍODO ---")
        
        # 1. Força a ida para a URL de Notas Emitidas
        # Adicionei um wait_until="load" para garantir que o menu carregou
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="load", timeout=60000)
        
        # 2. Pequena pausa para o JavaScript do portal "assentar"
        page.wait_for_timeout(5000)

        # 3. Se ainda não encontrar o seletor, tenta recarregar a URL uma vez
        try:
            page.wait_for_selector("input[name*='DataEmissaoInicio']", timeout=10000)
        except:
            print("-> Campo não apareceu. Tentando recarregar a página de consulta...")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle")
            page.wait_for_selector("input[name*='DataEmissaoInicio']", timeout=20000)

        # Converte as datas de AAAA-MM-DD (HTML) para DD/MM/AAAA (Portal) se necessário
        if '-' in data_inicio:
            ano_i, mes_i, dia_i = data_inicio.split('-')
            data_inicio = f"{dia_i}/{mes_i}/{ano_i}"
        
        if '-' in data_fim:
            ano_f, mes_f, dia_f = data_fim.split('-')
            data_fim = f"{dia_f}/{mes_f}/{ano_f}"

        # Preenchimento garantido: Limpa e Digita
        page.locator("input[name*='DataEmissaoInicio']").fill("")
        page.locator("input[name*='DataEmissaoInicio']").type(data_inicio, delay=50)
        
        page.locator("input[name*='DataEmissaoFim']").fill("")
        page.locator("input[name*='DataEmissaoFim']").type(data_fim, delay=50)

        print(f"-> Aplicando filtros no portal...")
        # Clica no botão de consulta (geralmente o botão principal de submit do form de filtros)
        page.click("button.btn-primary, button[type='submit']")
        
        # Aguarda a tabela atualizar
        page.wait_for_timeout(5000)
        page.wait_for_selector("table tbody", timeout=30000)

        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => ({
                index: i,
                texto: row.innerText,
                // Tenta capturar o ID diretamente do HTML caso já esteja lá (data-chave)
                html: row.innerHTML
            })).filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'));
        }""")
        
        print(f"Notas detectadas após filtro: {len(notas)}")
        return notas
    except Exception as e:
        print(f"Erro na consulta: {e}")
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
