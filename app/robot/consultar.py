import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Formato que o portal mais aceita via digitação
        data_inicio = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"Tentando acessar consulta: {data_inicio} a {data_fim}")

        # 2. Navegação com tentativa de "desbloqueio"
        # Vamos para a página de notas emitidas
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # Se houver algum botão de "Entrar" ou "Contribuinte" sobrando, clicamos
        if page.locator("text=Contribuinte").is_visible():
            page.locator("text=Contribuinte").first.click()
            page.wait_for_timeout(2000)

        # 3. Localizar os campos de data (Busca por texto de Label)
        # Em vez de 'input[name]', vamos buscar o input que está PERTO do texto 'Data de Início'
        print("Buscando campos de data via labels...")
        
        # Tentativa 1: Localizar pelo texto do Label (mais humano)
        try:
            input_inicio = page.get_by_label("Data de Início").first or \
                           page.get_by_label("Período de Emissão - Início").first or \
                           page.get_by_placeholder("Data Inicial").first
            
            input_inicio.wait_for(state="visible", timeout=15000)
        except:
            # Tentativa 2: Seletor Genérico se o Label falhar
            print("Label não encontrado, tentando seletores de fallback...")
            input_inicio = page.locator("input[type='text']").nth(0) # Geralmente o primeiro campo de texto na tela de filtros

        # 4. Preenchimento
        print("Preenchendo datas...")
        input_inicio.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(data_inicio, delay=100)
        
        # O campo de fim costuma ser o próximo (Tab) ou o segundo input
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)
        page.keyboard.type(data_fim, delay=100)
        page.keyboard.press("Enter")

        # 5. Clicar em Filtrar
        # Se o Enter não bastar, clicamos no botão
        btn_filtrar = page.locator("button:has-text('Filtrar'), .btn-primary:has-text('Filtrar')").first
        if btn_filtrar.is_visible():
            btn_filtrar.click()
        
        # 6. Captura de Resultados
        print("Aguardando tabela...")
        page.wait_for_timeout(5000)

        notas = []
        # O portal pode demorar a renderizar a tabela
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto = linha.inner_text().strip()
            if not texto or "Nenhum registro" in texto:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) >= 1:
                numero = colunas[0].inner_text().split('\n')[0].strip()
                notas.append({"numero": numero, "linha": linha, "index": i})

        print(f"Sucesso: {len(notas)} notas listadas.")
        return notas

    except Exception as e:
        # Essencial para entender o que o robô está vendo no Railway
        page.screenshot(path="/tmp/erro_view.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # Clique no menu de ações (três pontos)
        # Em algumas telas é um ícone de 'lupa' ou 'engrenagem'
        btn_acoes = nota["linha"].locator("button, a").last
        btn_acoes.click()
        page.wait_for_timeout(1000)

        with page.expect_download(timeout=30000) as download_info:
            # Tentamos baixar pelo texto exato que você mencionou
            page.locator("text=Download XML").first.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        raise Exception(f"Erro no download XML {nota['numero']}: {str(e)}")
