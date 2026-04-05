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

        # 1. Localiza TODOS os botões de ações (dropdowns) da página
        # O seletor .dropdown-toggle é o padrão desse portal para os três pontos
        botoes_acoes = page.locator(".dropdown-toggle, button[data-toggle='dropdown'], .btn-sm i.fa-cog, .btn-sm i.fa-ellipsis-v")
        
        if botoes_acoes.count() <= idx:
            print(f"   [ERRO] Botão de ação para o índice {idx} não encontrado.")
            return False

        # 2. Clica no botão correspondente ao índice da nota
        print(f"   Abrindo menu de ações...")
        botoes_acoes.nth(idx).click(force=True, timeout=15000)
        
        # Espera o menu expandir
        page.wait_for_timeout(2000)

        # 3. Localizar o link de XML que APARECEU na tela
        # Agora buscamos o link de forma global, pois o menu dropdown costuma ser 
        # renderizado no final do HTML, fora da tabela.
        link_xml = page.locator("a:has-text('Download XML')").first
        
        # Fallback caso o texto varie
        if not link_xml.is_visible():
            link_xml = page.locator("a[href*='Download/NFSe']").first

        print(f"   Clicando no link de download...")
        
        try:
            with page.expect_download(timeout=60000) as download_info:
                # Usamos dispatch_event('click') como cartada final se o click() falhar
                link_xml.dispatch_event("click")
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] Nota {nota['numero']} salva com sucesso!")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] Falha ao capturar download: {e_dl}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        page.keyboard.press("Escape")
        return False
