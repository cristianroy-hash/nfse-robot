import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparação das Datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Formato DDMMAAAA para preenchimento de campos com máscara
        data_ini = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"--- INICIANDO CONSULTA DIRETA ---")
        print(f"Período: {data_ini} a {data_fim}")

        # 2. SALTO DIRETO PARA A PÁGINA DE NOTAS
        # Evitamos clicar no menu 'Consultar' que está dando timeout
        print("Navegando diretamente para a URL de notas emitidas...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        # 3. DIAGNÓSTICO DA TELA DE FILTRO
        url_atual = page.url
        print(f"URL alcançada: {url_atual}")
        
        # 4. LOCALIZAR CAMPOS DE DATA
        # Usamos seletores variados para garantir que pegamos os inputs de data
        print("Aguardando campos de data...")
        selector_data = "input.data, .form-control.data, input[placeholder*='/'], input[name*='Data']"
        
        try:
            page.wait_for_selector(selector_data, state="visible", timeout=30000)
            inputs = page.locator(selector_data).all()
            
            if len(inputs) >= 2:
                print(f"Campos encontrados: {len(inputs)}. Preenchendo datas...")
                # Preenche Início e Fim
                for i, campo in enumerate([inputs[0], inputs[1]]):
                    valor = data_ini if i == 0 else data_fim
                    campo.click()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(valor, delay=70)
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(500)

                # 5. CLICAR EM FILTRAR
                print("Clicando no botão Filtrar...")
                # Tentamos por ID ou por texto
                btn_filtrar = page.locator("#btnFiltrar, button:has-text('Filtrar'), .btn-primary").first
                btn_filtrar.click()
                
                # Aguarda a tabela atualizar
                print("Aguardando processamento do filtro...")
                page.wait_for_timeout(5000)
            else:
                print(f"ERRO: Apenas {len(inputs)} campos de data encontrados.")
                page.screenshot(path="/tmp/campos_nao_encontrados.png")

        except Exception as e_campos:
            print(f"Não foi possível interagir com os campos de data: {str(e_campos)}")
            page.screenshot(path="/tmp/erro_interacao_campos.png")

        # 6. COLETAR RESULTADOS DA TABELA
        notas_encontradas = []
        # Localiza as linhas da tabela de resultados
        linhas = page.locator("table tbody tr").all()
        
        for linha in linhas:
            texto_linha = linha.inner_text().strip()
            # Ignora linhas vazias ou mensagens de "nenhum registro"
            if "Nenhum registro" in texto_linha or not texto_linha or len(texto_linha) < 10:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                # O número da nota costuma ser a primeira coluna
                num_nota = colunas[0].inner_text().split('\n')[0].strip()
                
                # Tenta capturar o link de download se ele estiver na linha (seu atalho)
                url_direta = linha.locator("a[href*='Download/NFSe/']").get_attribute("href")
                full_url = None
                if url_direta:
                    full_url = url_direta if url_direta.startswith("http") else f"https://www.nfse.gov.br{url_direta}"

                notas_encontradas.append({
                    "numero": num_nota,
                    "linha": linha,
                    "url_download": full_url
                })

        print(f"Consulta finalizada. Notas detectadas para processamento: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_critico_consulta.png")
        print(f"Falha detalhada: {traceback.format_exc()}")
        raise Exception(f"Erro na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    """
    Realiza o download do arquivo XML da nota.
    """
    try:
        print(f"Baixando XML da nota {nota['numero']}...")
        caminho_final = os.path.join(download_dir, f"{nota['numero']}.xml")

        # Prioridade 1: Link direto (se capturado na tabela)
        if nota.get("url_download"):
            try:
                with page.expect_download(timeout=20000) as download_info:
                    page.goto(nota["url_download"])
                download = download_info.value
                download.save_as(caminho_final)
                return True
            except:
                print("Link direto falhou, tentando via menu de ações...")

        # Prioridade 2: Menu de Três Pontos (Clique manual)
        # 1. Clica no botão de ações (três pontos) na linha da nota
        btn_acoes = nota["linha"].locator("button i.fa-ellipsis-v, button.dropdown-toggle, [title*='Ações']").first
        btn_acoes.click()
        page.wait_for_timeout(1500)

        # 2. Clica na opção de Download XML
        link_download = page.locator("a:has-text('Download XML'), [href*='Download/NFSe/']").first
        with page.expect_download(timeout=45000) as download_info:
            link_download.click()

        download = download_info.value
        download.save_as(caminho_final)
        
        # Fecha o menu para a próxima nota
        page.keyboard.press("Escape")
        return True

    except Exception as e:
        print(f"Falha no download da nota {nota['numero']}: {str(e)}")
        return False
