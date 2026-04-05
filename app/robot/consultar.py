import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Configurar Período
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        data_ini = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"

        print(f"Iniciando consulta: {data_ini} a {data_fim}")

        # 2. Navegação via Menu
        print("Navegando pelos menus...")
        page.locator("a:has-text('Consultar'), .menu-item:has-text('Consultar')").first.click()
        page.wait_for_timeout(1000)
        page.locator("a:has-text('Notas Emitidas'), [href*='Emitidas']").first.click()
        
        # 3. Preenchimento de Datas
        page.wait_for_selector("input.data, .form-control.data", timeout=45000)
        inputs = page.locator("input.data, .form-control.data").all()
        
        for i, campo in enumerate([inputs[0], inputs[1]]):
            valor = data_ini if i == 0 else data_fim
            campo.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(valor, delay=50)
            page.keyboard.press("Tab")

        # 4. Filtrar
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar'), .btn-primary").first.click()
        page.wait_for_timeout(5000) # Aguarda processamento

        # --- DIAGNÓSTICO TEMPORÁRIO (Inserido aqui) ---
        url_atual = page.url
        texto = page.evaluate("() => document.body.innerText.substring(0, 1500)")
        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a'))
                .map(a => ({ text: a.innerText.trim().substring(0,50), href: a.href }))
                .filter(a => a.text && a.href.includes('http'));
        }""")
        print(f"--- DEBUG CONSULTA ---")
        print(f"URL atual: {url_atual}")
        print(f"Texto da página: {texto[:500]}...") # Primeiros 500 chars para não poluir
        print(f"Links encontrados: {links}")
        print(f"--- FIM DEBUG ---")
        # ----------------------------------------------

        # 5. Coleta das Notas
        notas_encontradas = []
        linhas = page.locator("table tbody tr").all()
        
        for linha in linhas:
            info_linha = linha.inner_text().strip()
            if "Nenhum registro" in info_linha or not info_linha:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                num = colunas[0].inner_text().split('\n')[0].strip()
                
                # Tenta capturar URL direta se o link de download já estiver na linha
                url_direta = linha.locator("a[href*='Download/NFSe/']").get_attribute("href")
                
                # Normaliza URL se for relativa
                full_url = None
                if url_direta:
                    full_url = url_direta if url_direta.startswith("http") else f"https://www.nfse.gov.br{url_direta}"

                notas_encontradas.append({
                    "numero": num, 
                    "linha": linha,
                    "url_download": full_url
                })

        print(f"Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Falha na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # A. Tentativa via URL Direta (Sua sugestão)
        if nota.get("url_download"):
            try:
                with page.expect_download(timeout=20000) as download_info:
                    page.goto(nota["url_download"])
                download = download_info.value
                download.save_as(os.path.join(download_dir, f"{nota['numero']}.xml"))
                return True
            except:
                print(f"URL direta falhou para nota {nota['numero']}, usando fallback...")

        # B. Fallback via Menu de Três Pontos
        btn_acoes = nota["linha"].locator("button i.fa-ellipsis-v, button.dropdown-toggle, [title*='Ações']").first
        btn_acoes.click()
        page.wait_for_timeout(1000)

        link_download = page.locator("a:has-text('Download XML'), [href*='Download/NFSe/']").first
        with page.expect_download(timeout=45000) as download_info:
            link_download.click()

        download = download_info.value
        download.save_as(os.path.join(download_dir, f"{nota['numero']}.xml"))
        page.keyboard.press("Escape")
        return True

    except Exception as e:
        print(f"Erro no download {nota['numero']}: {str(e)}")
        return False
