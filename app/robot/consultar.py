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

        # 1. Localiza a linha e rola até ela
        linha = page.locator("table tbody tr").nth(idx)
        linha.scroll_into_view_if_needed()

        # 2. Busca o botão de ações na última coluna da linha (o ícone verde/engrenagem do print)
        # O seletor busca qualquer link ou botão na última célula (td) da linha
        btn_acoes = linha.locator("td").last.locator("button, a, i").first

        print(f"   Abrindo menu de ações...")
        # Forçamos o clique via dispatch_event para evitar que o menu feche sozinho
        btn_acoes.dispatch_event("click")
        
        # Espera o menu renderizar
        page.wait_for_timeout(2500)

        # 3. Localizar o link de XML que apareceu no menu suspenso
        # Buscamos globalmente por qualquer link que tenha "XML" no texto
        link_xml = page.locator("a:has-text('XML')").first

        print(f"   Disparando download...")
        
        try:
            with page.expect_download(timeout=60000) as download_info:
                # Clique via JavaScript para garantir a captura do evento de download
                page.evaluate("el => el.click()", link_xml.element_handle())
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [SUCESSO] {nota['numero']}.xml baixado!")
            return True
        except Exception as e_dl:
            print(f"   [AVISO] Falha ao clicar no download ou timeout: {e_dl}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"   [ERRO] Falha no processo: {e}")
        page.keyboard.press("Escape")
        return False
