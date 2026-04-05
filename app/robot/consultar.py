import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        data_inicio = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"Acessando consulta com filtros técnicos: {data_inicio} a {data_fim}")

        # 2. Navegar direto para a URL de Notas Emitidas
        # Usamos uma espera longa para garantir que o portal "acorde"
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=90000)
        
        # 3. Localizar os campos usando a classe que você encontrou (.btn-calendario)
        # Geralmente o input de data está dentro ou logo após esse botão/classe
        print("Localizando campos via classe .btn-calendario...")
        
        # Esperamos o seletor que você identificou
        page.wait_for_selector(".btn-calendario", timeout=30000)
        
        # O portal nacional usa inputs com IDs específicos para Início e Fim.
        # Vamos tentar pelo seletor CSS de atributo que contém 'Data'
        inputs_data = page.locator("input[class*='calendario'], .btn-calendario input, input[name*='Data']").all()
        
        if len(inputs_data) >= 2:
            input_ini = inputs_data[0]
            input_fim = inputs_data[1]
        else:
            # Fallback caso os inputs não estejam dentro da classe
            input_ini = page.locator("input[name='DataInicio']").first
            input_fim = page.locator("input[name='DataFim']").first

        # 4. Preenchimento Robusto
        for i, campo in enumerate([input_ini, input_fim]):
            valor = data_inicio if i == 0 else data_fim
            campo.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(valor, delay=100)
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)

        # 5. Clicar no botão Filtrar (Geralmente btn-primary)
        page.locator("button:has-text('Filtrar'), .btn-primary").first.click()
        
        # 6. Aguardar e Coletar
        page.wait_for_timeout(5000)
        notas = []
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            if "Nenhum registro" in linha.inner_text():
                break
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                # O número da nota costuma ser o primeiro texto da primeira coluna
                numero = colunas[0].inner_text().split('\n')[0].strip()
                notas.append({"numero": numero, "linha": linha})

        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_tecnico.png")
        raise Exception(f"Falha na consulta técnica: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # Usando a lógica dos 3 pontos que você viu no portal
        btn_acoes = nota["linha"].locator("button[title='Ações'], .btn-group button").first
        btn_acoes.click()
        page.wait_for_timeout(1000)

        # O seletor de download que você identificou como texto
        with page.expect_download(timeout=45000) as download_info:
            # Tentamos pelo texto exato do menu suspenso
            page.get_by_text("Download XML").click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        raise Exception(f"Erro no download: {str(e)}")
