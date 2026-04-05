import os
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        ano_str, mes_str = competencia.split("-")
        ano, mes = int(ano_str), int(mes_str)
        ultimo_dia = monthrange(ano, mes)[1]
        data_ini = f"01/{mes:02d}/{ano}"
        data_fim = f"{ultimo_dia:02d}/{mes:02d}/{ano}"
        print(f"Período: {data_ini} a {data_fim}")

        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Preenche datas via JavaScript diretamente
        preencheu = page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input[type="text"], input[type="date"]');
            let preenchidos = 0;
            inputs.forEach((inp, i) => {{
                if (i === 0) {{ inp.value = '{data_ini}'; preenchidos++; }}
                if (i === 1) {{ inp.value = '{data_fim}'; preenchidos++; }}
            }});
            return preenchidos;
        }}""")
        print(f"Campos preenchidos via JS: {preencheu}")

        # Clica no botão filtrar
        try:
            page.locator("button:has-text('Filtrar')").first.click()
            page.wait_for_timeout(4000)
        except:
            print("Botão filtrar não encontrado, usando tabela atual...")

        # Captura todas as URLs de download direto da página via JavaScript
        urls_download = page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="Download/NFSe"]');
            return Array.from(links).map(a => ({
                href: a.href,
                text: a.innerText.trim()
            }));
        }""")
        print(f"URLs de download encontradas: {len(urls_download)}")
        for u in urls_download:
            print(f"  {u}")

        # Monta lista de notas com URLs diretas
        notas = []
        for i, url_info in enumerate(urls_download):
            href = url_info["href"]
            # Extrai número da nota da URL
            numero = href.split("/")[-1] if href else f"nota_{i}"
            notas.append({
                "numero": numero,
                "url_download": href,
                "linha": None
            })

        print(f"Total de notas: {len(notas)}")
        return notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        print(f"Baixando nota {nota['numero']}...")
        url = nota.get("url_download")
        if not url:
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{nota['numero']}.xml")

        with page.expect_download(timeout=60000) as download_info:
            page.goto(url)

        download = download_info.value
        download.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar {nota['numero']}: {str(e)}")
        return False
