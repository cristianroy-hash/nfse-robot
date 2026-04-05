import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        # Captura as linhas da tabela usando JavaScript para ser mais rápido e evitar erros de seletor
        notas_indices = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr');
            const validIndices = [];
            rows.forEach((row, index) => {
                const text = row.innerText.trim();
                if (text && !text.includes('Nenhum registro')) {
                    validIndices.push(index);
                }
            });
            return validIndices;
        }""")

        notas_encontradas = []
        for idx in notas_indices:
            # Pegamos o número da nota apenas para nomear o arquivo
            try:
                numero = page.locator("table tbody tr").nth(idx).locator("td").first.inner_text().split('\\n')[0].strip()
            except:
                numero = f"nota_{idx}"
            
            notas_encontradas.append({
                "numero": numero,
                "index": idx
            })

        print(f"Sucesso! Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        caminho_local = os.path.join(download_dir, f"{nota['numero']}.xml")
        print(f"Processando download da nota índice {idx} ({nota['numero']})")

        # 1. Clicar no botão de ações da linha específica usando JS DIRETO
        # O seletor '.dropdown-toggle' é o padrão desse portal
        success_click = page.evaluate(f"""(index) => {{
            const row = document.querySelectorAll('table tbody tr')[index];
            const btn = row.querySelector('.dropdown-toggle') || row.querySelector('button') || row.querySelector('a[data-toggle]');
            if (btn) {{
                btn.click();
                return true;
            }}
            return false;
        }}""", idx)

        if not success_click:
            return False

        page.wait_for_timeout(2000)

        # 2. Clicar no Download XML que apareceu
        # Usamos expect_download para capturar o arquivo
        try:
            with page.expect_download(timeout=30000) as download_info:
                # Clica no link que contém 'Download XML'
                page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a'));
                    const dlLink = links.find(a => a.innerText.includes('Download XML'));
                    if (dlLink) dlLink.click();
                }""")
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"Download ok: {nota['numero']}")
            return True
        except:
            print(f"Não conseguiu clicar no link de download da nota {idx}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"Erro no download: {e}")
        page.keyboard.press("Escape")
        return False
