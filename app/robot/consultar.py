import os
import time

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        notas = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('table tbody tr'))
                .map((row, i) => ({ index: i, texto: row.innerText }))
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
        print(f"-> Acionando nota {idx} e aguardando menu...")

        # 1. Clica na linha para ativar o popover
        linha = page.locator("table tbody tr").nth(idx)
        linha.click()
        
        # 2. AGUARDAR O LINK APARECER (A mágica está aqui)
        # Em vez de evaluate imediato, esperamos o seletor do link que você achou
        # O seletor abaixo busca um link 'a' cujo 'href' contenha 'Download/NFSe'
        seletor_xml = 'a[href*="Download/NFSe"]:not([href*="DANFSe"])'
        
        try:
            # Espera até 15 segundos para o site injetar o link no HTML
            page.wait_for_selector(seletor_xml, state="attached", timeout=15000)
            
            # 3. Agora que sabemos que o link existe, pegamos o href dele
            href = page.locator(seletor_xml).first.get_attribute("href")
            
            if href:
                # Garante que o link seja absoluto
                if href.startswith('/'):
                    href = f"https://www.nfse.gov.br{href}"
                
                id_nota = href.split('/')[-1]
                print(f"   [SUCESSO] Link XML detectado via seletor: ...{id_nota[-10:]}")
                caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

                with page.expect_download(timeout=60000) as download_info:
                    page.goto(href)
                
                download_info.value.save_as(caminho_local)
                print(f"   [OK] XML {id_nota[:8]} salvo!")
                
                # Fecha o popover para não encavalar na próxima nota
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
                return True
            
        except Exception as e_timeout:
            print(f"   [AVISO] Menu não abriu a tempo para nota {idx}. Tentando clique forçado no ícone...")
            # Plano B: Tenta clicar especificamente no que parecer um botão/ícone na linha
            linha.locator("i, button, a").last.click()
            page.wait_for_timeout(3000)
            # Tenta uma última vez capturar qualquer link de download
            href_final = page.evaluate('document.querySelector(\'a[href*="Download/NFSe"]:not([href*="DANFSe"])\')?.href')
            if href_final:
                # (Repete a lógica de download se achar aqui - simplificado para o exemplo)
                page.goto(href_final) 
                return True

        print(f"   [ERRO] Link XML não apareceu para a nota {idx}")
        return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        return False
