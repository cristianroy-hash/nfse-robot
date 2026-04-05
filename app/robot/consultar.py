import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        data_ini = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"--- CONSULTA OPERACIONAL ---")

        # 2. Ir para a página de consulta
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # 3. Tentar exibir os campos de filtro (caso estejam escondidos)
        # Alguns perfis precisam clicar em um botão para expandir os filtros
        btn_expandir = page.locator("button:has-text('Filtros'), .btn-filtros, #btnFiltros").first
        if btn_expandir.is_visible():
            btn_expandir.click()
            page.wait_for_timeout(1000)

        # 4. Preencher Datas com Seletor Flexível
        selector_data = "input.data, .form-control.data, input[placeholder*='/'], input[name*='Data']"
        
        try:
            # Espera curta para os campos
            page.wait_for_selector(selector_data, state="visible", timeout=15000)
            inputs = page.locator(selector_data).all()
            
            if len(inputs) >= 2:
                for i, campo in enumerate([inputs[0], inputs[1]]):
                    valor = data_ini if i == 0 else data_fim
                    campo.click()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(valor, delay=50)
                    page.keyboard.press("Tab")

                page.locator("button:has-text('Filtrar'), .btn-primary, #btnFiltrar").first.click()
                page.wait_for_timeout(5000)
        except:
            print("Aviso: Campos de filtro não encontrados ou já processados.")

        # 5. Coleta Segura (O ajuste principal aqui)
        notas_encontradas = []
        # Aguarda a tabela existir
        if page.locator("table tbody tr").first.is_visible(timeout=10000):
            linhas = page.locator("table tbody tr").all()
            
            for linha in linhas:
                texto = linha.inner_text().strip()
                if "Nenhum registro" in texto or not texto: continue
                
                colunas = linha.locator("td").all()
                if len(colunas) > 0:
                    num_nota = colunas[0].inner_text().split('\n')[0].strip()
                    
                    # BUSCA SEGURA DO LINK (Sem travar se não achar)
                    url_direta = None
                    link_el = linha.locator("a[href*='Download/NFSe/']").first
                    if link_el.count() > 0:
                        url_direta = link_el.get_attribute("href")
                    
                    full_url = None
                    if url_direta:
                        full_url = url_direta if url_direta.startswith("http") else f"https://www.nfse.gov.br{url_direta}"

                    notas_encontradas.append({
                        "numero": num_nota,
                        "linha": linha,
                        "url_download": full_url
                    })

        print(f"Notas prontas para download: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta_final.png")
        print(f"Erro detalhado: {traceback.format_exc()}")
        raise Exception(f"Falha na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")

        # 1. Tenta Link Direto (se existir)
        if nota.get("url_download"):
            try:
                with page.expect_download(timeout=15000) as dl:
                    page.goto(nota["url_download"])
                dl.value.save_as(caminho)
                return True
            except: pass

        # 2. Fallback: Menu de Ações (O "balé" dos 3 pontos)
        # Garante que a linha está visível antes de clicar
        nota["linha"].scroll_into_view_if_needed()
        btn = nota["linha"].locator("button i.fa-ellipsis-v, button.dropdown-toggle, [title*='Ações']").first
        btn.click()
        page.wait_for_timeout(1000)

        # Clica no link de Download que aparece no menu
        link_dl = page.locator("a:has-text('Download XML'), [href*='Download/NFSe/']").first
        with page.expect_download(timeout=30000) as dl:
            link_dl.click()
        
        dl.value.save_as(caminho)
        page.keyboard.press("Escape")
        return True
    except Exception as e:
        print(f"Erro download nota {nota.get('numero')}: {str(e)}")
        return False
