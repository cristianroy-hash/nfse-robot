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
        print(f"-> Tentando baixar nota index {idx} ({nota['numero']})")

        # 1. Garantir que a linha está visível e centralizada
        linha = page.locator("table tbody tr").nth(idx)
        linha.scroll_into_view_if_needed()
        
        # 2. Clicar no botão de Ações (Dropdown)
        # No print, é aquele botão na última coluna
        btn_acoes = linha.locator("button.dropdown-toggle, a.dropdown-toggle, .btn-sm").first
        
        # Tentativa de clique com espera
        btn_acoes.click(force=True, timeout=10000)
        
        # Espera o menu aparecer (fundamental!)
        page.wait_for_timeout(2000)

        # 3. Localizar o link de XML no menu suspenso
        # Usamos uma expressão regular para ignorar maiúsculas/minúsculas
        link_xml = page.get_by_role("link").filter(has_text="Download XML").first
        
        # Caso o seletor acima falhe, tentamos um seletor CSS de fallback
        if not link_xml.is_visible():
            link_xml = page.locator("a:has-text('XML')").first

        print(f"   Clicando no link de download...")
        
        try:
            with page.expect_download(timeout=60000) as download_info:
                # O clique final
                link_xml.click(force=True, timeout=5000)
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] Nota {nota['numero']} salva!")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] O link de download não respondeu: {e_dl}")
            # Tira um print do erro para diagnóstico se estiver no seu servidor
            page.screenshot(path=f"/tmp/erro_dl_{idx}.png")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] Falha no processo: {e}")
        page.keyboard.press("Escape")
        return False
