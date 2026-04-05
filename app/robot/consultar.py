import os

def consultar_notas(page, competencia: str):
    try:
        # A competência vem no formato YYYY-MM
        ano, mes = competencia.split("-")
        competencia_formatada = f"{mes}/{ano}"
        
        print(f"Iniciando consulta para a competência: {competencia_formatada}")

        # 1. Navega para a URL de consulta
        # Nota: Verifique se a URL termina em /NotaFiscal/Consultar ou /Notas/Consultar
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/NotaFiscal/Consultar",
            wait_until="networkidle",
            timeout=60000
        )
        
        # Aguarda um pouco para scripts internos do portal
        page.wait_for_timeout(3000)

        # 2. Tenta encontrar o campo de Competência por diferentes seletores comuns no portal
        # O portal às vezes usa 'Competencia', 'DataCompetencia' ou 'DataInicio'
        seletor_sucesso = None
        possiveis_seletores = [
            "input[name='Competencia']",
            "input[id='Competencia']",
            "input[name='DataCompetencia']",
            "input[id='DataCompetencia']",
            ".datepicker-input" # Seletor genérico de data do portal
        ]

        for seletor in possiveis_seletores:
            try:
                if page.is_visible(seletor, timeout=2000):
                    seletor_sucesso = seletor
                    break
            except:
                continue

        if seletor_sucesso:
            print(f"Campo de competência encontrado via: {seletor_sucesso}")
            page.fill(seletor_sucesso, "") # Limpa antes
            page.fill(seletor_sucesso, competencia_formatada)
            # Em alguns casos é preciso apertar 'Tab' ou 'Enter' para o portal validar a data
            page.keyboard.press("Tab")
        else:
            # Se não achou, vamos tentar procurar por texto no label
            print("Tentando localizar campo via label texto...")
            page.get_by_label("Competência").fill(competencia_formatada)

        # 3. Clica em pesquisar/consultar
        # O botão pode ser 'Consultar', 'Pesquisar' ou ter um ícone de lupa
        botao_busca = page.get_by_role("button", name="Consultar") or \
                      page.get_by_role("button", name="Pesquisar") or \
                      page.locator("button[type='submit']")
        
        botao_busca.first.click()
        
        # Aguarda os resultados carregarem
        page.wait_for_timeout(5000)

        # 4. Coleta as notas da tabela
        notas = []
        # O seletor da tabela no portal nacional costuma ser bem específico
        linhas = page.locator("table tbody tr").all()
        
        print(f"Linhas encontradas na tabela: {len(linhas)}")
        
        for i, linha in enumerate(linhas):
            try:
                # Tenta pegar o número da nota (geralmente primeira ou segunda coluna)
                texto_linha = linha.inner_text().strip()
                if "Nenhum registro encontrado" in texto_linha:
                    break
                
                colunas = linha.locator("td").all()
                numero = colunas[0].inner_text().strip() if colunas else f"nota_{i}"
                
                notas.append({
                    "numero": numero,
                    "linha": linha, # Guardamos o locator da linha para o clique de download
                    "index": i
                })
            except Exception as e:
                print(f"Erro ao processar linha {i}: {str(e)}")
                continue

        print(f"Total de notas processadas: {len(notas)}")
        return notas

    except Exception as e:
        # Tira um screenshot do erro para ajudar no debug (salva no container)
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # No portal nacional, o ícone de XML costuma ser um link ou botão com 'xml' no nome ou título
        # Usamos locators flexíveis
        btn_xml = nota["linha"].locator("a:has-text('XML')").first or \
                  nota["linha"].locator("button[title*='XML']").first or \
                  nota["linha"].locator("i.fa-file-code").first # Ícone comum de código/xml

        with page.expect_download(timeout=30000) as download_info:
            btn_xml.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        
        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        return conteudo

    except Exception as e:
        raise Exception(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
