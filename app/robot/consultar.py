import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        # 1. Preparar as datas
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        
        data_inicio = f"01/{mes:02d}/{ano}"
        data_fim = f"{ultimo_dia:02d}/{mes:02d}/{ano}"
        
        print(f"Tentando acessar painel para: {data_inicio} a {data_fim}")

        # 2. Forçar entrada no Emissor Nacional
        # Às vezes o portal autentica mas não redireciona. Vamos forçar a URL de entrada.
        page.goto("https://www.nfse.gov.br/EmissorNacional/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Se ainda estiver na tela de login, tentamos clicar no botão de certificado de novo
        # (Isso aproveita o certificado que já está no 'context')
        if "Login" in page.url:
            print("Ainda na tela de login. Forçando clique no acesso por certificado...")
            btn_cert = page.locator("text=Acesso com certificado digital").first
            if btn_cert.is_visible():
                btn_cert.click()
                page.wait_for_timeout(5000)

        # 3. Esperar o painel carregar (tentando múltiplos sinais de sucesso)
        print("Aguardando confirmação de login (Sair ou Consultar)...")
        try:
            # Esperamos ou o botão Sair ou o link de consulta aparecerem
            page.wait_for_selector("text=Sair, text=Emitir, text=Consultar", timeout=20000)
        except:
            print("Aviso: Timeout ao esperar 'Sair'. Tentando prosseguir mesmo assim...")

        # 4. Ir direto para a URL de Notas Emitidas
        # Isso costuma 'pular' menus que não carregam
        print("Navegando direto para Notas Emitidas...")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle")
        
        # 5. Preencher Filtros
        print("Preenchendo campos de data...")
        input_inicio = page.locator("input[name='DataInicio'], #DataInicio").first
        input_fim = page.locator("input[name='DataFim'], #DataFim").first
        
        input_inicio.wait_for(state="visible", timeout=15000)
        
        # Simula digitação para ativar máscaras do portal
        input_inicio.click()
        input_inicio.fill("")
        input_inicio.type(data_inicio, delay=50)
        
        input_fim.click()
        input_fim.fill("")
        input_fim.type(data_fim, delay=50)
        
        # 6. Filtrar
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar'), button:has-text('Pesquisar')").first.click()
        page.wait_for_timeout(4000)

        # 7. Coleta das Notas
        notas = []
        linhas = page.locator("table tbody tr").all()
        
        for i, linha in enumerate(linhas):
            texto = linha.inner_text().strip()
            if not texto or "Nenhum registro" in texto:
                continue
            
            colunas = linha.locator("td").all()
            if colunas:
                numero = colunas[0].inner_text().strip()
                notas.append({"numero": numero, "linha": linha, "index": i})

        print(f"Total de notas encontradas: {len(notas)}")
        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_final.png")
        raise Exception(f"Falha ao consultar notas: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    # (Mantém a mesma lógica anterior de clicar em ações -> Download XML)
    try:
        # Tenta clicar no botão de ações (geralmente tem um ícone de 'lista' ou 'três pontos')
        btn_acoes = nota["linha"].locator("button").last
        btn_acoes.click()
        page.wait_for_timeout(1000)

        with page.expect_download(timeout=30000) as download_info:
            page.locator("text=Download XML").first.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        return True
    except Exception as e:
        raise Exception(f"Erro no download XML {nota['numero']}: {str(e)}")
