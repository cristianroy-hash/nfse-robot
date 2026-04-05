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

        # 1. Localiza a linha da nota novamente para garantir foco
        linha = page.locator("table tbody tr").nth(idx)
        linha.scroll_into_view_if_needed()

        # 2. SELETOR ULTRA-ABRANGENTE:
        # Procuramos por qualquer botão, link ou ícone que pareça um menu de ações
        # dentro da linha específica da nota.
        btn_acoes = linha.locator("button, a, i").filter(has_text="").filter(
            lambda el: el.get_attribute("class") and ("dropdown" in el.get_attribute("class") or "cog" in el.get_attribute("class") or "ellipsis" in el.get_attribute("class"))
        ).first
        
        # Caso o filtro acima seja muito restrito, tentamos o clique direto na última célula
        # onde geralmente ficam as ações (baseado no seu print)
        if not btn_acoes.is_visible():
             btn_acoes = linha.locator("td").last.locator("a, button").first

        print(f"   Abrindo menu de ações via clique forçado...")
        # Usamos dispatch_event para garantir que o clique ocorra mesmo se houver algo na frente
        btn_acoes.dispatch_event("click")
        
        page.wait_for_timeout(2500) # Tempo extra para o menu abrir

        # 3. Localizar o link de XML de forma agressiva
        # Procuramos por qualquer elemento que contenha 'XML' no texto ou no atributo
        link_xml = page.locator("a:has-text('XML'), button:has-text('XML'), [title*='XML']").first

        print(f"   Disparando download...")
        
        try:
            with page.expect_download(timeout=60000) as download_info:
                # O segredo: usamos o clique de evento do JS para evitar que o menu feche antes do tempo
                page.evaluate("el => el.click()", link_xml.element_handle())
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [SUCESSO] Arquivo salvo: {nota['numero']}.xml")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] O clique no download falhou ou o site não respondeu: {e_dl}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        page.keyboard.press("Escape")
        return False
