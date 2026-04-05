import os
import time

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # Aguarda a tabela e garante que as linhas existam
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        notas = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('table tbody tr'))
                .map((row, i) => ({ 
                    index: i, 
                    texto: row.innerText 
                }))
                .filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'))
                .map(r => ({ index: r.index, numero: `nota_${r.index}` }));
        }""")
        
        print(f"Notas detectadas: {len(notas)}")
        return notas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        print(f"-> Acionando nota {idx} para revelar menu...")

        # 1. Clica na linha para ativar a classe 'selecionada' e abrir o popover
        linha = page.locator("table tbody tr").nth(idx)
        linha.click()
        
        # 2. Pequena pausa para o sistema injetar o HTML do popover que você viu
        page.wait_for_timeout(2000)

        # 3. Busca o link XML usando a estrutura exata que você encontrou no console
        # Procuramos por um link que contenha 'Download/NFSe' (XML) e NÃO 'DANFSe' (PDF)
        href = page.evaluate("""() => {
            // Busca o link dentro do popover ou em qualquer lugar que tenha aparecido após o clique
            const links = Array.from(document.querySelectorAll('a[href*="Download/NFSe"]'));
            // Filtra para garantir que pegamos o XML e não o DANFSe (PDF)
            const linkXml = links.find(a => a.href.includes('/Download/NFSe/') && !a.href.includes('DANFSe'));
            return linkXml ? linkXml.href : null;
        }""")

        if href:
            # Extrai o ID (aquela sequência longa de números) para o nome do arquivo
            id_nota = href.split('/')[-1]
            print(f"   [SUCESSO] Link XML localizado: ...{id_nota[-10:]}")
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            # 4. Realiza o download
            try:
                with page.expect_download(timeout=60000) as download_info:
                    page.goto(href)
                
                download = download_info.value
                download.save_as(caminho_local)
                print(f"   [OK] Arquivo XML salvo!")
                
                # Clica fora ou aperta ESC para fechar o popover e não atrapalhar a próxima
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                return True
            except Exception as e_dl:
                print(f"   [ERRO] Falha no download do arquivo: {e_dl}")
                return False
        else:
            print(f"   [ERRO] Não foi possível encontrar o link XML no popover da nota {idx}")
            # Tira um print interno (opcional) ou tenta voltar
            return False

    except Exception as e:
        print(f"   [FALHA NO PROCESSO] {e}")
        return False
