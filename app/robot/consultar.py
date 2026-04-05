import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas (Início e Fim do mês)
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Formato DD/MM/YYYY que o portal costuma aceitar melhor visualmente
        data_inicio = f"01/{mes:02d}/{ano}"
        data_fim = f"{ultimo_dia:02d}/{mes:02d}/{ano}"
        
        print(f"Iniciando busca: {data_inicio} até {data_fim}")

        # 2. Garantir que estamos na home do emissor e esperar o painel
        page.goto("https://www.nfse.gov.br/EmissorNacional/", wait_until="domcontentloaded")
        
        # Espera qualquer sinal de que o login foi processado (procure por um texto comum no painel)
        page.wait_for_selector("text=Sair", timeout=30000)

        # 3. Clicar em "NFS-e Emitidas" usando um seletor de texto mais flexível
        # Tentamos clicar no link que contém o texto, independente de ser 'role link' ou não
        print("Acessando área de Notas Emitidas...")
        area_emitidas = page.locator("text=NFS-e Emitidas").first
        area_emitidas.click(timeout=30000)
        
        # 4. Preencher Data Inicial e Final
        # Usamos wait_for_load_state para garantir que o formulário de filtro carregou
        page.wait_for_load_state("networkidle")
        
        print("Preenchendo datas...")
        # Seletores por ID ou Name costumam ser mais estáveis após o clique
        input_inicio = page.locator("input[name='DataInicio'], input#DataInicio").first
        input_fim = page.locator("input[name='DataFim'], input#DataFim").first
        
        input_inicio.wait_for(state="visible", timeout=20000)
        
        # Limpa e preenche
        input_inicio.fill("")
        input_inicio.type(data_inicio, delay=100)
        
        input_fim.fill("")
        input_fim.type(data_fim, delay=100)
        
        # 5. Clicar no botão "Filtrar"
        # Às vezes o botão tem o nome 'Filtrar' ou 'Pesquisar'
        btn_filtrar = page.locator("button:has-text('Filtrar'), button:has-text('Pesquisar')").first
        btn_filtrar.click()
        
        # 6. Aguarda os resultados
        print("Aguardando resultados da tabela...")
        page.wait_for_timeout(5000)

        notas = []
        # Localiza as linhas da tabela (ignorando o cabeçalho)
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto_linha = linha.inner_text()
            if "Nenhum registro" in texto_linha or not texto_linha.strip():
                continue
            
            # Pega o número da nota (geralmente na primeira coluna)
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                numero = colunas[0].inner_text().strip()
                notas.append({
                    "numero": numero,
                    "linha": linha,
                    "index": i
                })

        print(f"Sucesso: {len(notas)} notas encontradas.")
        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta_detalhado.png")
        print(f"Erro capturado. Screenshot salvo em /tmp/erro_consulta_detalhado.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # 1. Localiza o botão de ações (os 3 pontos/engrenagem)
        # Procure por um botão dentro da linha da nota
        btn_acoes = nota["linha"].locator("button").last # Geralmente o último botão da linha são as ações
        btn_acoes.click()
        page.wait_for_timeout(1500)

        # 2. Clica no item de menu "Download XML"
        with page.expect_download(timeout=30000) as download_info:
            page.locator("text=Download XML").first.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        
        return True

    except Exception as e:
        raise Exception(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
