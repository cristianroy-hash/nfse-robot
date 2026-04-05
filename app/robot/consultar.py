import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        # Recarrega a página para limpar qualquer erro de sessão anterior
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        # Captura apenas índices de linhas que REALMENTE parecem notas
        notas_indices = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr');
            return Array.from(rows)
                .map((row, i) => ({ text: row.innerText, index: i }))
                .filter(item => item.text.length > 10 && !item.text.includes('Exception') && !item.text.includes('Nenhum registro'))
                .map(item => item.index);
        }""")

        notas_encontradas = []
        for idx in notas_indices:
            try:
                raw_text = page.locator("table tbody tr").nth(idx).locator("td").first.inner_text()
                # Se o texto for gigante (erro do site), limpa
                numero = raw_text.split('\n')[0].strip()
                if len(numero) > 50 or "exception" in numero.lower():
                    numero = f"nota_idx_{idx}"
            except:
                numero = f"nota_{idx}"
            
            notas_encontradas.append({"numero": numero, "index": idx})

        print(f"Notas detectadas após filtro de erro: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        caminho_local = os.path.join(download_dir, f"{nota['numero']}.xml")
        print(f"Baixando nota: {nota['numero']}")

        # 1. Abre o menu de ações usando o índice
        # Buscamos o botão que abre o dropdown na linha correta
        linha = page.locator("table tbody tr").nth(idx)
        btn_acoes = linha.locator(".dropdown-toggle, button, a[data-toggle]").first
        
        # Clique forçado para garantir que o menu abra
        btn_acoes.click(force=True, timeout=10000)
        page.wait_for_timeout(1500)

        # 2. Clica no Download XML
        # O seletor "has-text" é o mais infalível para esse portal
        link_xml = page.locator("a:has-text('Download XML')").first
        
        try:
            with page.expect_download(timeout=45000) as download_info:
                # Se o clique normal falhar, o force=True ignora se o menu está 'meio' aberto
                link_xml.click(force=True)
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"Arquivo salvo com sucesso: {nota['numero']}.xml")
            return True
        except Exception as e_inner:
            print(f"Não conseguiu disparar o download: {e_inner}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"Erro no processo de download: {e}")
        page.keyboard.press("Escape")
        return False
