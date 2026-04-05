import os
import time

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # Aguarda a tabela
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        # Extração avançada: busca a chave em links e textos
        notas_encontradas = page.evaluate("""() => {
            const rows = Array.from(document.querySelectorAll('table tbody tr'));
            return rows.map((row, i) => {
                const texto = row.innerText;
                if (texto.length < 10 || texto.includes('Nenhum registro')) return null;

                // Busca chave de 44 dígitos no texto ou em atributos de links (href)
                let chave = null;
                const matchChave = texto.match(/\\d{44}/);
                if (matchChave) {
                    chave = matchChave[0];
                } else {
                    // Tenta buscar no atributo 'href' de algum link dentro da linha
                    const link = row.querySelector('a[href*="chaveAcesso="], a[href*="ChaveAcesso="]');
                    if (link) {
                        const urlMatch = link.href.match(/\\d{44}/);
                        if (urlMatch) chave = urlMatch[0];
                    }
                }

                const numeroMatch = texto.match(/^\\d+/);
                return {
                    index: i,
                    numero: numeroMatch ? numeroMatch[0] : `nota_${i}`,
                    chave: chave
                };
            }).filter(n => n !== null);
        }""")

        print(f"Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        numero = nota.get("numero")
        caminho_local = os.path.join(download_dir, f"{numero}.xml")
        
        # Se não temos a chave, vamos tentar "caçar" ela clicando na linha
        if not nota.get("chave"):
            print(f"   [INFO] Chave oculta para nota {numero}. Tentando extrair via clique...")
            nota["chave"] = extrair_chave_via_clique(page, nota["index"])

        if not nota["chave"]:
            print(f"   [ERRO] Não foi possível obter a chave da nota {numero}")
            return False

        print(f"-> Baixando via URL Direta: {nota['chave']}")
        url_direta = f"https://www.nfse.gov.br/EmissorNacional/NFSes/Download/XML?chaveAcesso={nota['chave']}"

        try:
            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] {numero}.xml salvo!")
            return True
        except Exception as e:
            print(f"   [ERRO] Download direto falhou: {e}")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        return False

def extrair_chave_via_clique(page, idx):
    """Clica na linha para ver se a chave aparece em algum lugar da tela"""
    try:
        # Clica na primeira célula da linha (geralmente o número da nota)
        page.locator("table tbody tr").nth(idx).locator("td").first.click()
        page.wait_for_timeout(2000)
        
        # Agora busca na página inteira por 44 dígitos
        corpo_texto = page.content()
        match = __import__('re').search(r'\d{44}', corpo_texto)
        if match:
            # Volta para a lista
            page.keyboard.press("Escape")
            return match.group(0)
        return None
    except:
        return None
