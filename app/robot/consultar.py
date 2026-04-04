def consultar_notas(page, competencia: str):
    try:
        # Navega para consulta de NFS-e
        page.goto("https://www.nfse.gov.br/EmissorNacional/NotaFiscal/Consultar", wait_until="networkidle")
        page.wait_for_timeout(2000)

        # Preenche competência (formato YYYY-MM)
        ano, mes = competencia.split("-")
        
        # Aguarda campo de competência aparecer
        page.wait_for_selector("input[name='competencia']", timeout=10000)
        page.fill("input[name='competencia']", f"{mes}/{ano}")

        # Clica em pesquisar
        page.click("button[type='submit']")
        page.wait_for_timeout(3000)

        # Coleta as notas listadas
        notas = []
        itens = page.query_selector_all(".nota-fiscal-item")
        
        for item in itens:
            numero = item.query_selector(".numero-nota")
            if numero:
                notas.append({
                    "numero": numero.inner_text().strip(),
                    "elemento": item
                })

        return notas

    except Exception as e:
        raise Exception(f"Falha ao consultar notas: {str(e)}")


def baixar_xml(page, nota: dict):
    try:
        # Clica no botão de download do XML da nota
        nota["elemento"].click()
        page.wait_for_timeout(1000)
        
        page.click("text=Download XML")
        page.wait_for_timeout(2000)

        # Captura o conteúdo XML
        xml_content = page.content()
        return xml_content

    except Exception as e:
        raise Exception(f"Falha ao baixar XML da nota {nota['numero']}: {str(e)}")
