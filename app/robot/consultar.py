import os

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("table tbody tr", timeout=30000)
        
        # Capturamos o índice e a Chave de Acesso (data-chave) de cada linha
        notas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => {
                // O site guarda a chave ou ID no atributo data-chave ou em links internos
                const linkXml = row.querySelector('a[href*="Download/NFSe"]')?.href;
                const chaveBruta = row.getAttribute('data-chave') || "";
                
                return {
                    index: i,
                    texto: row.innerText,
                    linkDireto: linkXml,
                    chaveBase64: chaveBruta
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
        # Se já pegamos o link na listagem, usamos ele direto!
        href = nota.get("linkDireto")
        
        if not href:
            # Se não tinha link na linha, forçamos o clique para o site gerar o link
            print(f"-> Ativando linha {nota['index']}...")
            page.locator("table tbody tr").nth(nota['index']).click()
            page.wait_for_timeout(2000)
            href = page.evaluate('document.querySelector(\'a[href*="Download/NFSe"]:not([href*="DANFSe"])\')?.href')

        if href:
            if href.startswith('/'): href = f"https://www.nfse.gov.br{href}"
            
            id_nota = href.split('/')[-1]
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            print(f"   [BAIXANDO] ID: {id_nota[:15]}...")
            with page.expect_download(timeout=60000) as download_info:
                page.goto(href)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML salvo!")
            return True
        
        print(f"   [ERRO] Link não disponível para a nota {nota['index']}")
        return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        return False
