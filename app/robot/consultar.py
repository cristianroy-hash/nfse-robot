import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Formato puro para digitar (Diyitaremos com delay)
        data_inicio = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"Tentando acesso direto: {data_inicio} a {data_fim}")

        # 2. Navegação com espera estendida
        # O portal nacional às vezes demora para validar o mTLS
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded", timeout=120000)
        
        # 3. Tratamento de "Tela de Seleção de Perfil"
        # Se o portal pedir para escolher quem está acessando (comum após login com certificado)
        try:
            perfil = page.locator("text=Contribuinte, .card-body").first
            if perfil.is_visible(timeout=5000):
                print("Detectada seleção de perfil. Clicando...")
                perfil.click()
                page.wait_for_timeout(3000)
        except:
            pass

        # 4. Localizar os campos usando a classe que você forneceu: form-control data
        print("Buscando campos .form-control.data...")
        
        # Esperamos o campo de texto que você identificou
        # Usamos um seletor que aceita as duas classes juntas
        input_locator = page.locator("input.form-control.data")
        
        # Espera até 60s para o formulário aparecer (o portal é lento)
        input_locator.first.wait_for(state="visible", timeout=60000)
        
        inputs = input_locator.all()
        
        if len(inputs) >= 2:
            input_ini = inputs[0]
            input_fim = inputs[1]
            
            print("Campos de data encontrados. Preenchendo...")
            
            for i, campo in enumerate([input_ini, input_fim]):
                valor = data_inicio if i == 0 else data_fim
                campo.click()
                # Limpeza profunda do campo
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.wait_for_timeout(200)
                # Digitação simulada
                page.keyboard.type(valor, delay=150)
                page.keyboard.press("Tab")
        else:
            raise Exception(f"Não foram encontrados os 2 campos de data. Encontrados: {len(inputs)}")

        # 5. Clicar no botão Filtrar
        # Usamos um seletor genérico para o botão principal de ação
        btn_filtrar = page.locator("button:has-text('Filtrar'), .btn-primary").first
        btn_filtrar.click()
        
        # 6. Aguardar e Coletar Resultados
        page.wait_for_timeout(6000)
        
        notas = []
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto = linha.inner_text().strip()
            if "Nenhum registro" in texto or not texto:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                numero = colunas[0].inner_text().split('\n')[0].strip()
                notas.append({"numero": numero, "linha": linha})

        print(f"Sucesso: {len(notas)} notas listadas.")
        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_classe_data.png")
        raise Exception(f"Falha na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    # Lógica de download baseada no menu de 3 pontos
    try:
        # Busca o botão de ações na linha da nota
        btn_acoes = nota["linha"].locator("button, .btn-group").last
        btn_acoes.click()
        page.wait_for_timeout(2000)

        with page.expect_download(timeout=60000) as download_info:
            # Busca o item de menu "Download XML"
            page.get_by_text("Download XML").click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        raise Exception(f"Erro no download: {str(e)}")
