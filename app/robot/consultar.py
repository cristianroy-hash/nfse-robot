import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    """
    Função principal de navegação e consulta de notas.
    Utiliza exploração dinâmica de links para encontrar o caminho correto.
    """
    try:
        # 1. Preparação das Datas
        # Formato esperado da competência: "YYYY-MM"
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        # Datas sem barras (geralmente melhor para campos com máscara)
        data_ini = f"01{mes:02d}{ano}"
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"--- INICIANDO EXPLORAÇÃO DE CONSULTA ---")
        print(f"Período Alvo: {data_ini} até {data_fim}")

        # 2. Mapeamento Dinâmico do Dashboard (Sua Estratégia)
        # Captura todos os links para não dependermos de seletores fixos que mudam
        links_pagina = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a'))
                .map(a => ({ 
                    text: a.innerText.trim(), 
                    href: a.href 
                }))
                .filter(a => a.text && a.href.includes('http'));
        }""")
        
        print("Links detectados no Dashboard para análise:")
        url_notas = None
        for l in links_pagina:
            texto_link = l["text"].lower()
            href_link = l["href"].lower()
            print(f"  > [{l['text']}] -> {l['href']}")
            
            # Lógica de busca: Priorizamos links que falem em "Emitidas" ou "Consultar"
            if "emitida" in texto_link or "emitidas" in href_link:
                url_notas = l["href"]
                print(f"  *** URL de Notas Emitidas Identificada: {url_notas} ***")
                break # Encontramos o alvo principal

        # 3. Navegação para a área de Notas
        if url_notas:
            print(f"Navegando para a URL identificada...")
            page.goto(url_notas, wait_until="networkidle", timeout=60000)
        else:
            print("Link específico não encontrado nos menus. Tentando URL padrão de contingência...")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")

        page.wait_for_timeout(3000)
        
        # 4. Diagnóstico Pós-Navegação
        url_atual = page.url
        texto_tela = page.evaluate("() => document.body.innerText.substring(0, 1000)")
        print(f"URL Atual: {url_atual}")
        print(f"Texto inicial da página: {texto_tela[:200]}...")

        # 5. Preenchimento do Formulário de Filtros
        print("Localizando campos de data...")
        # Seletores flexíveis: classe .data, .form-control ou pelo placeholder de data
        selector_data = "input.data, .form-control.data, input[placeholder*='/'], input[name*='Data']"
        
        try:
            page.wait_for_selector(selector_data, timeout=20000)
            inputs = page.locator(selector_data).all()
            
            if len(inputs) >= 2:
                print(f"Preenchendo período: {data_ini} a {data_fim}")
                # Preenche Data Início e Data Fim
                for i, campo in enumerate([inputs[0], inputs[1]]):
                    valor = data_ini if i == 0 else data_fim
                    campo.click()
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(valor, delay=60)
                    page.keyboard.press("Tab")
                    page.wait_for_timeout(500)

                # 6. Acionar Filtro
                print("Clicando no botão Filtrar...")
                btn_filtrar = page.locator("button:has-text('Filtrar'), .btn-primary, #btnFiltrar").first
                btn_filtrar.click()
                
                # Aguarda o carregamento dos resultados
                page.wait_for_timeout(5000)
                print("Filtro aplicado. Analisando resultados...")
            else:
                print(f"Aviso: Encontrados apenas {len(inputs)} campos de data. Verifique a estrutura.")
        
        except Exception as e_form:
            print(f"Erro ao interagir com o formulário: {str(e_form)}")

        # 7. Coleta de Notas (Baseado na estrutura de tabela padrão)
        notas_encontradas = []
        linhas = page.locator("table tbody tr").all()
        
        for linha in linhas:
            texto_linha = linha.inner_text().strip()
            if "Nenhum registro" in texto_linha or not texto_linha:
                continue
            
            colunas = linha.locator("td").all()
            if len(colunas) > 0:
                num_nota = colunas[0].inner_text().split('\n')[0].strip()
                
                # Tenta capturar link de download direto se ele estiver visível na linha
                url_direta = linha.locator("a[href*='Download/NFSe/']").get_attribute("href")
                full_url = None
                if url_direta:
                    full_url = url_direta if url_direta.startswith("http") else f"https://www.nfse.gov.br{url_direta}"

                notas_encontradas.append({
                    "numero": num_nota,
                    "linha": linha,
                    "url_download": full_url
                })

        print(f"Fim do processo. Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consultar_completo.png")
        print(f"DETALHES DO ERRO: {traceback.format_exc()}")
        raise Exception(f"Falha crítica na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    """
    Lógica de download para cada nota individual.
    Tenta URL direta e possui fallback para o menu de ações (três pontos).
    """
    try:
        print(f"Iniciando download da nota: {nota['numero']}")

        # Caminho final do arquivo
        caminho_arquivo = os.path.join(download_dir, f"{nota['numero']}.xml")

        # Estratégia 1: URL Direta
        if nota.get("url_download"):
            try:
                print(f"Tentando download via link direto...")
                with page.expect_download(timeout=20000) as download_info:
                    page.goto(nota["url_download"])
                download = download_info.value
                download.save_as(caminho_arquivo)
                print(f"Sucesso via link direto: {nota['numero']}")
                return True
            except Exception as e_url:
                print(f"Link direto falhou, tentando via menu... ({str(e_url)})")

        # Estratégia 2: Menu de Ações (Três Pontos)
        # Localiza o botão que abre o dropdown na linha específica da nota
        btn_acoes = nota["linha"].locator("button i.fa-ellipsis-v, button.dropdown-toggle, [title*='Ações']").first
        btn_acoes.click()
        page.wait_for_timeout(1000)

        # Busca o link de download que apareceu no menu suspenso
        link_download = page.locator("a:has-text('Download XML'), [href*='Download/NFSe/']").first
        
        with page.expect_download(timeout=45000) as download_info:
            link_download.click()

        download = download_info.value
        download.save_as(caminho_arquivo)
        
        # Fecha o menu para não atrapalhar a próxima linha
        page.keyboard.press("Escape")
        
        print(f"Sucesso via menu de ações: {nota['numero']}")
        return True

    except Exception as e:
        print(f"Falha ao baixar nota {nota['numero']}: {str(e)}")
        return False
