import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(3000)

        # Captura cirúrgica de IDs e Chaves
        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => {
                // Tenta extrair o ID numérico longo de qualquer lugar da linha (href ou texto)
                const html = row.innerHTML;
                const matchId = html.match(/\\/([0-9]{40,50})/); 
                const idRecuperado = matchId ? matchId[1] : null;

                return {
                    index: i,
                    texto: row.innerText,
                    idNota: idRecuperado
                };
            }).filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'));
        }""")
        
        print(f"Notas detectadas: {len(notas)}")
        return notas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        id_nota = nota.get("idNota")

        # Se não pegamos o ID na varredura, tentamos "forçar" a aparição dele
        if not id_nota:
            print(f"-> ID não achado na linha {idx}. Forçando clique para carregar código...")
            page.locator("table tbody tr").nth(idx).click()
            page.wait_for_timeout(2000)
            id_nota = page.evaluate(`() => {
                const match = document.body.innerHTML.match(/\\/Download\\/NFSe\\/([0-9]{40,50})/);
                return match ? match[1] : null;
            }`)

        if id_nota:
            # Construímos a URL baseada no manual que você enviou e no seu teste de console
            url_direta = f"https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/{id_nota}"
            print(f"   [ALVO] URL Reconstruída: ...{id_nota[-10:]}")
            
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML salvo com sucesso!")
            return True
        else:
            print(f"   [ERRO] Não foi possível extrair o ID da nota {idx} mesmo após clique.")
            return False

    except Exception as e:
        print(f"   [FALHA] Erro ao processar nota {nota['index']}: {e}")
        return False
