import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas (Início e Fim do mês)
        # Ex: '2026-03' -> ano=2026, mes=3
        ano, mes = map(int, competencia.split("-"))
        ultimo_dia = monthrange(ano, mes)[1]
        
        data_inicio = f"01{mes:02d}{ano}" # Formato sem barras para o fill costuma ser mais seguro
        data_fim = f"{ultimo_dia:02d}{mes:02d}{ano}"
        
        print(f"Iniciando fluxo: {data_inicio} até {data_fim}")

        # 2. Navegar para o Painel (após login já realizado)
        # Se já estiver na página, o goto apenas confirma
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle")
        
        # 3. Clicar no botão "NFS-e Emitidas" 
        # (Caso o goto não tenha caído direto, reforçamos o clique no menu)
        btn_emitidas = page.get_by_role("link", name="NFS-e Emitidas") or \
                       page.locator("text=NFS-e Emitidas")
        btn_emitidas.first.click()
        page.wait_for_timeout(2000)

        # 4. Preencher Data Inicial e Final
        # No portal, os nomes costumam ser 'DataInicio' e 'DataFim'
        print("Preenchendo filtros de data...")
        page.wait_for_selector("input[name='DataInicio']", timeout=15000)
        
        page.fill("input[name='DataInicio']", data_inicio)
        page.fill("input[name='DataFim']", data_fim)
        
        # 5. Clicar no botão "Filtrar"
        page.get_by_role("button", name="Filtrar").click()
        
        # Aguarda a tabela atualizar
        page.wait_for_timeout(4000)

        # 6. Coleta as linhas da tabela resultante
        notas = []
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto = linha.inner_text()
            if "Nenhum registro" in texto:
                break
            
            # Tenta pegar o número da nota na primeira coluna
            colunas = linha.locator("td").all()
            numero = colunas[0].inner_text().strip() if colunas else f"nota_{i}"
            
            notas.append({
                "numero": numero,
                "linha": linha,
                "index": i
            })

        print(f"Notas encontradas: {len(notas)}")
        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_fluxo_consulta.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        # 1. Clicar no ícone de 3 botões/pontos (Ações)
        # Geralmente é um botão no final da linha ou um ícone de engrenagem/menu
        btn_acoes = nota["linha"].locator("button[title='Ações']").first or \
                    nota["linha"].locator(".btn-group button").first
        
        btn_acoes.click()
        page.wait_for_timeout(1000)

        # 2. Selecionar "Download XML" no menu que abriu
        with page.expect_download(timeout=30000) as download_info:
            page.locator("text=Download XML").first.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        
        return True

    except Exception as e:
        raise Exception(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
