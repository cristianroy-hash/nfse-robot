import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # Aguarda a tabela aparecer
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        # Detecta linhas válidas (que não sejam mensagens de "vazio")
        notas_encontradas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => ({
                index: i,
                texto: row.innerText
            })).filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'))
               .map(r => ({ index: r.index, numero: `nota_${r.index}` }));
        }""")

        print(f"Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        print(f"-> Abrindo detalhes da nota {idx}...")

        # ESTRATÉGIA DE CLIQUE DIRETO NA CÉLULA (Contorna erros de seletor)
        # Clicamos na primeira célula da linha, onde costuma estar o link/número
        celula_numero = page.locator("table tbody tr").nth(idx).locator("td").first
        celula_numero.click(timeout=15000) 
        
        # Espera carregar a página de detalhes
        page.wait_for_timeout(4000)
        
        # Captura todo o texto da página para achar a chave
        # Usamos o evaluate para pegar o texto limpo do DOM
        html_completo = page.evaluate("document.body.innerText")
        
        # Busca padrão de 44 dígitos
        match = re.search(r'\d{44}', html_completo)
        
        if not match:
            print("   [AVISO] Chave não achada no texto. Tentando inspecionar links...")
            html_links = page.evaluate("document.body.innerHTML")
            match = re.search(r'\d{44}', html_links)

        if match:
            chave = match.group(0)
            print(f"   Chave encontrada: {chave}")
            
            # URL de download direto (confirmada nos manuais)
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/NFSes/Download/XML?chaveAcesso={chave}"
            caminho_local = os.path.join(download_dir, f"{chave}.xml")

            try:
                with page.expect_download(timeout=60000) as download_info:
                    page.goto(url_direta)
                
                download = download_info.value
                download.save_as(caminho_local)
                print(f"   [OK] XML salvo!")
            except Exception as e_dl:
                print(f"   [ERRO] Falha no download da chave {chave}: {e_dl}")
        else:
            print(f"   [ERRO] Chave de 44 dígitos não localizada para nota {idx}")

        # VOLTA PARA A LISTA (Importante para o loop continuar)
        print("   Voltando para a lista...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded")
        page.wait_for_selector("table tbody tr", timeout=20000)
        return True # Retornamos True para o loop seguir para a próxima nota

    except Exception as e:
        print(f"   [ERRO NO PROCESSO] {e}")
        # Tenta voltar para não travar as próximas
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
        return False
