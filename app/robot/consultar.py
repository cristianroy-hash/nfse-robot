def consultar_notas(page, competencia: str):
    try:
        ano, mes = competencia.split("-")
        
        # Navega para consulta de notas
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/NotaFiscal/Consultar",
            wait_until="networkidle"
        )
        page.wait_for_timeout(2000)

        # Preenche filtro de competência
        page.wait_for_selector("input[name='Competencia']", timeout=10000)
        page.fill("input[name='Competencia']", f"{mes}/{ano}")

        # Clica em pesquisar
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)

        # Coleta links/botões de download de cada nota
        notas = []
        linhas = page.query_selector_all("table tbody tr")
        
        for i, linha in enumerate(linhas):
            try:
                numero_el = linha.query_selector("td:first-child")
                numero = numero_el.inner_text().strip() if numero_el else f"nota_{i}"
                notas.append({"numero": numero, "linha": linha, "index": i})
            except:
                continue

        print(f"Notas encontradas: {len(notas)}")
        return notas

    except Exception as e:
        raise Exception(f"Falha ao consultar notas: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    import os
    try:
        # Clica no botão de download XML da linha
        btn_xml = nota["linha"].query_selector("a[href*='xml'], button[title*='XML'], a[title*='XML']")
        
        if not btn_xml:
            raise Exception("Botão XML não encontrado")

        with page.expect_download() as download_info:
            btn_xml.click()
        
        download = download_info.value
        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")
        download.save_as(caminho)
        
        with open(caminho, 'r', encoding='utf-8') as f:
            conteudo = f.read()
        
        return conteudo

    except Exception as e:
        raise Exception(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
