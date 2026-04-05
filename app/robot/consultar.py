import os
import time

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        # Navega para a tela de notas emitidas
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # Aguarda a tabela carregar de fato
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        # Extrai os dados das notas (Número e Chave de Acesso)
        # A chave de acesso geralmente está no texto da linha ou em um atributo data-chave
        notas_encontradas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => {
                const texto = row.innerText;
                // Procura por uma sequência de 44 números (Padrão da Chave de Acesso)
                const chaveMatch = texto.match(/\\d{44}/);
                const numeroMatch = texto.match(/^\\d+/); // O número da nota costuma ser o primeiro campo
                
                if (texto.length < 10 || texto.includes('Nenhum registro')) return null;

                return {
                    index: i,
                    numero: numeroMatch ? numeroMatch[0] : `nota_${i}`,
                    chave: chaveMatch ? chaveMatch[0] : null
                };
            }).filter(n => n !== null);
        }""")

        print(f"Sucesso! Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        chave = nota.get("chave")
        numero = nota.get("numero")
        caminho_local = os.path.join(download_dir, f"{numero}.xml")

        if not chave:
            print(f"   [AVISO] Chave não encontrada para nota {numero}. Tentando método visual...")
            # Fallback caso não encontre a chave no texto
            return _baixar_visual_fallback(page, nota, caminho_local)

        print(f"-> Baixando via URL Direta (API): {numero}")
        
        # A URL de download direto baseada no manual/padrão do sistema
        url_direta = f"https://www.nfse.gov.br/EmissorNacional/NFSes/Download/XML?chaveAcesso={chave}"

        try:
            with page.expect_download(timeout=60000) as download_info:
                # Em vez de clicar, forçamos a navegação para a URL de download
                page.goto(url_direta)
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] {numero}.xml salvo com sucesso!")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] Falha no download direto: {e_dl}")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        return False

def _baixar_visual_fallback(page, nota, caminho_local):
    """Método de segurança caso a chave de acesso não seja capturada"""
    try:
        idx = nota["index"]
        # Tenta clicar na última célula (Ações)
        linha = page.locator("table tbody tr").nth(idx)
        linha.locator("td").last.click(timeout=5000)
        page.wait_for_timeout(1000)
        
        with page.expect_download(timeout=30000) as download_info:
            page.locator("a:has-text('XML'), button:has-text('XML')").first.click()
        
        download = download_info.value
        download.save_as(caminho_local)
        return True
    except:
        return False
