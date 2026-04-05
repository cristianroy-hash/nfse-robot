import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar Datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Datas sem barras para preenchimento mais seguro em campos com máscara
        data_ini = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"--- CONSULTA OPERACIONAL: {competencia} ---")

        # 2. Navegação Direta
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # 3. Preenchimento Robusto (Simulando usuário real)
        # Procuramos por campos que pareçam datas
        selector_data = "input.data, .form-control.data, input[placeholder*='/'], input[name*='Data']"
        
        try:
            page.wait_for_selector(selector_data, state="visible", timeout=15000)
            inputs = page.locator(selector_data).all()
            
            if len(inputs) >= 2:
                print(f"Preenchendo datas: {data_ini} e {data_fim}")
                for i, valor in enumerate([data_ini, data_fim]):
                    inputs[i].click()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(valor, delay=60)
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(500)

                # Clicar em Filtrar
                page.locator("button:has-text('Filtrar'), #btnFiltrar, .btn-primary").first.click()
                page.wait_for_timeout(5000)
            else:
                print("Campos de data não encontrados da forma esperada. Verificando se há notas na tela...")
        except Exception as e_filtro:
            print(f"Aviso no filtro: {e_filtro}")

        # 4. Coleta das Notas da Tabela
        notas_encontradas = []
        # Espera a tabela carregar os resultados
        page.wait_for_selector("table tbody tr", timeout=10000)
        linhas = page.locator("table tbody tr").all()
        
        for linha in linhas:
            texto_linha = linha.inner_text().strip()
            # Ignora avisos de "nada encontrado" ou linhas vazias
            if "Nenhum registro" in texto_linha or not texto_linha or len(texto_linha) < 10:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                # Pega o número da nota (geralmente primeira coluna)
                num_nota = colunas[0].inner_text().split('\n')[0].strip()
                
                # Guardamos a referência da LINHA para o baixar_xml clicar nela depois
                notas_encontradas.append({
                    "numero": num_nota,
                    "linha": linha
                })

        print(f"Sucesso! Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        print(f"Erro detalhado na consulta: {traceback.format_exc()}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        print(f"Iniciando download da nota: {nota['numero']}")
        caminho_local = os.path.join(download_dir, f"{nota['numero']}.xml")

        # 1. Localiza a linha
        linha = nota["linha"]
        linha.scroll_into_view_if_needed()
        
        # 2. SELETOR AJUSTADO: No print, o botão de ações é um link ou botão 
        # que geralmente fica na última coluna. Vamos buscar pelo ícone de engrenagem
        # ou pela classe de dropdown do portal.
        btn_acoes = linha.locator("a[data-toggle='dropdown'], button[data-toggle='dropdown'], i.fa-cog, i.fa-ellipsis-v").first
        
        # Forçamos o clique via JS porque esses botões de grade às vezes têm 
        # overlays invisíveis que bloqueiam o clique do Playwright
        page.evaluate("el => el.click()", btn_acoes.element_handle())
        page.wait_for_timeout(1000)

        # 3. SELETOR DO DOWNLOAD: O print mostra o texto exato "<> Download XML"
        # O seletor "has-text" é o mais seguro aqui.
        btn_download = page.locator("a:has-text('Download XML')").first
        
        if not btn_download.is_visible():
            # Tenta um seletor alternativo caso o texto mude levemente
            btn_download = page.locator("a[href*='Download/NFSe']").first

        print(f"Clicando no link de XML para a nota {nota['numero']}...")
        
        with page.expect_download(timeout=60000) as download_info:
            page.evaluate("el => el.click()", btn_download.element_handle())
        
        download = download_info.value
        download.save_as(caminho_local)
        
        # Fecha o menu para não atrapalhar a próxima linha
        page.keyboard.press("Escape")
        print(f"Sucesso: {nota['numero']}.xml baixado.")
        return True

    except Exception as e:
        print(f"Falha na nota {nota.get('numero')}: {str(e)}")
        page.keyboard.press("Escape")
        return False
