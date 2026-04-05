import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA VIA PERÍODO (Competência {competencia}) ---")
        # Ajustando para a URL de consulta detalhada
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # 1. Preenchimento por Datas (Baseado na sua sugestão de ser mais fácil)
        # Assumindo que a competência venha como '2026-03'
        ano, mes = competencia.split('-')
        data_ini = f"01/{mes}/{ano}"
        data_fim = f"31/{mes}/{ano}" # Simplificado, o portal costuma aceitar 31 para todos

        print(f"-> Filtrando de {data_ini} até {data_fim}...")
        
        # Seleciona filtro por data e preenche (IDs comuns nesses portais)
        page.fill("input[name*='DataEmissaoInicio']", data_ini)
        page.fill("input[name*='DataEmissaoFim']", data_fim)
        page.click("button[type='submit']")
        
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(3000)

        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => ({
                index: i,
                texto: row.innerText
            })).filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'));
        }""")
        
        print(f"Notas detectadas: {len(notas)}")
        return notas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    # Lista para armazenar o ID capturado via rede
    capturado = {"id": None}

    # Interceptador de Respostas de Rede (Pega o ID quando ele viaja do servidor)
    def check_network(response):
        if "Download/NFSe" in response.url or "Visualizar" in response.url:
            match = re.search(r'/([0-9]{40,60})', response.url)
            if match:
                capturado["id"] = match.group(1)

    try:
        idx = nota["index"]
        page.on("response", check_network)
        
        print(f"-> Forçando ativação da nota {idx}...")
        linha = page.locator("table tbody tr").nth(idx)
        
        # Tenta clicar no botão de ações ou na linha
        linha.click()
        page.wait_for_timeout(3000)

        # Se não pegou na rede, tenta o plano C: Atributo data-chave que você viu
        if not capturado["id"]:
            capturado["id"] = page.evaluate(f"""() => {{
                const row = document.querySelectorAll('table tbody tr')[{idx}];
                const href = row.innerHTML.match(/Download\/NFSe\/([0-9]{{40,60}})/);
                return href ? href[1] : null;
            }}""")

        if capturado["id"]:
            id_nota = capturado["id"]
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/{id_nota}"
            print(f"   [SUCESSO] ID capturado: ...{id_nota[-10:]}")
            
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")
            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML salvo!")
            page.remove_listener("response", check_network)
            return True
        else:
            print(f"   [ERRO] Nota {idx} não revelou o ID.")
            page.remove_listener("response", check_network)
            return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        return False
