import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

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
        print(f"-> Tentando extrair chave da nota {idx}...")

        # 1. Clica na célula para abrir detalhes
        celula = page.locator("table tbody tr").nth(idx).locator("td").first
        celula.click(timeout=15000)
        page.wait_for_timeout(4000)

        # 2. VARREDURA TOTAL (Busca a chave no HTML, em Inputs e no Texto)
        chave = page.evaluate("""() => {
            // Função para achar 44 números seguidos
            const regex = /\\d{44}/;
            
            // Busca em todo o HTML da página
            const htmlMatch = document.documentElement.innerHTML.match(regex);
            if (htmlMatch) return htmlMatch[0];

            // Busca em todos os campos de texto (Inputs)
            const inputs = Array.from(document.querySelectorAll('input, textarea'));
            for (let i of inputs) {
                const valMatch = i.value.match(regex);
                if (valMatch) return valMatch[0];
            }
            
            return null;
        }""")

        if chave:
            print(f"   [SUCESSO] Chave identificada: {chave}")
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/NFSes/Download/XML?chaveAcesso={chave}"
            caminho_local = os.path.join(download_dir, f"{chave}.xml")

            try:
                with page.expect_download(timeout=60000) as download_info:
                    page.goto(url_direta)
                download = download_info.value
                download.save_as(caminho_local)
                print(f"   [OK] XML salvo com sucesso!")
            except Exception as e_dl:
                print(f"   [ERRO] Falha no download direto: {e_dl}")
        else:
            print(f"   [ERRO] Não foi possível localizar a chave de 44 dígitos no HTML da nota {idx}")

        # 3. Retorno seguro para a lista
        print("   Retornando para a lista principal...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded")
        page.wait_for_selector("table tbody tr", timeout=20000)
        return True

    except Exception as e:
        print(f"   [FALHA NO PROCESSO] {e}")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
        return False
