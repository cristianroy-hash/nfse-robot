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

        print(f"Iniciando consulta para o período: {data_ini} a {data_fim}")

        # 2. Navegação via Menu (Mais seguro contra Erro 500)
        print("Navegando pelos menus...")
        page.get_by_role("link", name="Consultar").first.click()
        page.wait_for_timeout(1000)
        page.get_by_role("link", name="Notas Emitidas").first.click()
        
        # 3. Localizar e Preencher Datas
        print("Aguardando campos de data (.form-control.data)...")
        page.wait_for_selector("input.form-control.data", timeout=45000)
        
        inputs = page.locator("input.form-control.data").all()
        if len(inputs) < 2:
            raise Exception(f"Campos de data não encontrados. Total: {len(inputs)}")

        for i, campo in enumerate([inputs[0], inputs[1]]):
            valor = data_ini if i == 0 else data_fim
            campo.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(valor, delay=100)
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)

        # 4. Filtrar
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar'), .btn-primary").first.click()
        page.wait_for_timeout(5000)

        # 5. Coletar Notas na Tabela
        notas_encontradas = []
        linhas = page.locator("table tbody tr").all()
        
        for linha in linhas:
            texto = linha.inner_text().strip()
            if "Nenhum registro" in texto or not texto:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                num = colunas[0].inner_text().split('\n')[0].strip()
                notas_encontradas.append({"numero": num, "linha": linha})

        print(f"Total de notas encontradas: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta_notas.png")
        raise Exception(f"Erro ao consultar notas: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # Tenta localizar o botão de download (ícone de nuvem ou texto XML)
        btn_download = nota["linha"].locator("button[title*='XML'], .btn-download, text='XML'").first
        
        with page.expect_download(timeout=60000) as download_info:
            btn_download.click()
            
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        print(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
        return False
