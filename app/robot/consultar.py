import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(3000)

        # Captura de dados da tabela via JavaScript puro
        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => {
                const html = row.innerHTML;
                // Busca o ID numérico longo (40 a 50 dígitos) no HTML da linha
                const matchId = html.match(/[0-9]{40,50}/); 
                const idRecuperado = matchId ? matchId[0] : null;

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

        # Se o ID não veio na varredura inicial, tentamos forçar o clique
        if not id_nota:
            print(f"-> ID não localizado na linha {idx}. Tentando clique para carregar...")
            page.locator("table tbody tr").nth(idx).click()
            page.wait_for_timeout(3000)
            
            # Busca o ID novamente no HTML total da página
            id_nota = page.evaluate("""() => {
                const bodyHtml = document.body.innerHTML;
                const match = bodyHtml.match(/Download\/NFSe\/([0-9]{40,50})/);
                return match ? match[1] : null;
            }""")

        if id_nota:
            # URL de download baseada na documentação técnica do ADN que você enviou
            url_direta = "https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/" + str(id_nota)
            print(f"   [ALVO] URL: ...{id_nota[-10:]}")
            
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            # Executa o download
            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] XML salvo com sucesso!")
            return True
        else:
            print(f"   [ERRO] ID da nota {idx} não encontrado no sistema.")
            return False

    except Exception as e:
        print(f"   [FALHA] Erro ao processar nota: {e}")
        return False
