import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # O portal costuma preferir o formato sem barras ou com barras dependendo do script
        # Vamos usar o formato DD/MM/YYYY que é o padrão visual
        data_inicio = f"01/{mes:02d}/{ano}"
        data_fim = f"{ultimo_dia:02d}/{mes:02d}/{ano}"
        
        print(f"Buscando notas de {data_inicio} até {data_fim}")

        # 2. Navegar para a URL de Notas Emitidas
        # Forçamos o recarregamento para garantir que a sessão do certificado está ativa
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        # 3. Esperar o formulário de filtros
        # Às vezes o ID do campo tem prefixos. Vamos usar seletores mais genéricos.
        print("Aguardando formulário de filtros...")
        
        # Tentamos múltiplos seletores para o campo de data
        input_inicio = page.locator("input[id*='DataInicio'], input[name*='DataInicio'], .datepicker-input").first
        
        # Espera o elemento estar não só presente, mas visível e editável
        input_inicio.wait_for(state="visible", timeout=30000)
        
        # 4. Preenchimento assistido (Clica, limpa e digita)
        print("Preenchendo filtros...")
        input_inicio.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        input_inicio.type(data_inicio, delay=100)
        
        input_fim = page.locator("input[id*='DataFim'], input[name*='DataFim']").first
        input_fim.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        input_fim.type(data_fim, delay=100)
        
        # Tab para sair do campo e disparar eventos de validação do portal
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)

        # 5. Clicar no botão Filtrar
        # O botão pode estar como 'Filtrar' ou apenas um ícone
        botao_filtrar = page.locator("button:has-text('Filtrar'), .btn-primary:has-text('Filtrar'), button[type='submit']").first
        botao_filtrar.click()
        
        # 6. Aguardar carregamento da tabela
        print("Aguardando resultados...")
        page.wait_for_timeout(5000)

        notas = []
        # Espera a tabela de resultados ou a mensagem de "Nenhum registro"
        # O seletor 'table tbody tr' é o mais comum
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto = linha.inner_text().strip()
            if not texto or "Nenhum registro" in texto:
                print("Nenhuma nota encontrada para este período.")
                break
            
            colunas = linha.locator("td").all()
            if len(colunas) > 1:
                # Geralmente o número da nota está na coluna 0 ou 1
                numero = colunas[0].inner_text().strip()
                notas.append({"numero": numero, "linha": linha, "index": i})

        print(f"Sucesso: {len(notas)} notas encontradas.")
        return notas

    except Exception as e:
        # Tira screenshot do estado atual da tela para vermos o que travou
        page.screenshot(path="/tmp/erro_detalhado_consulta.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # No portal nacional, as ações ficam num botão de 'três pontos' ou 'engrenagem'
        # Vamos tentar clicar no último botão da linha (geralmente é o de ações)
        btn_acoes = nota["linha"].locator("button").last
        btn_acoes.click()
        page.wait_for_timeout(1500)

        # Clica no texto "Download XML" que aparece no menu suspenso
        with page.expect_download(timeout=30000) as download_info:
            page.locator("text=Download XML").first.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        raise Exception(f"Erro no download XML {nota['numero']}: {str(e)}")
