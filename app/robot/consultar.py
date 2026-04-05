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

# No loop de notas, antes de baixar:
page.wait_for_selector("table tbody tr", timeout=30000)

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        caminho_local = os.path.join(download_dir, f"{nota['numero']}.xml")
        print(f"-> Disparando download via JS Injection: {nota['numero']}")

        # 1. Executamos um script que faz tudo: abre o menu e clica no download
        # Isso ignora problemas de visibilidade ou overlays do Playwright
        script_download = f"""
        () => {{
            const rows = document.querySelectorAll('table tbody tr');
            const row = rows[{idx}];
            if (!row) return "ROW_NOT_FOUND";

            // Acha o botão de ações na linha (última célula)
            const actionsBtn = row.querySelector('td:last-child button') || 
                               row.querySelector('td:last-child a') || 
                               row.querySelector('.dropdown-toggle');
            
            if (!actionsBtn) return "BTN_NOT_FOUND";
            
            actionsBtn.click(); // Abre o menu
            
            // Pequeno delay para o menu aparecer no DOM e clica no XML
            setTimeout(() => {{
                const links = Array.from(document.querySelectorAll('a, button'));
                const xmlLink = links.find(el => el.innerText.includes('XML'));
                if (xmlLink) xmlLink.click();
            }}, 500);
            
            return "SUCCESS";
        }}
        """

        try:
            with page.expect_download(timeout=60000) as download_info:
                res = page.evaluate(script_download)
                if res != "SUCCESS":
                    print(f"   [AVISO] JS retornou: {res}")
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] Download concluído: {nota['numero']}")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] Timeout no download (site lento ou menu não abriu): {e_dl}")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        return False
