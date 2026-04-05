import os
import re
from datetime import datetime

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Converte formato YYYY-MM-DD para DD/MM/YYYY que o portal espera
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        # Navega direto para a página de notas emitidas
        # URL descoberta via diagnóstico dos links do dashboard
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Preenche data inicial usando ID descoberto via diagnóstico
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        campo_ini.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_ini_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Preenche data final usando ID descoberto via diagnóstico
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        campo_fim.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_fim_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Verifica se os valores foram preenchidos corretamente
        val_ini = page.locator("#datainicio").input_value()
        val_fim = page.locator("#datafim").input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # Clica no botão Filtrar para aplicar o período
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(6000)

        # Captura notas usando data-chave descoberto no diagnóstico do HTML
        # A tabela usa data-chave (base64) em vez de data-id
        notas_raw = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-chave]');
            return Array.from(rows).map(row => {
                const chaveEncoded = row.getAttribute('data-chave');
                const situacao = row.getAttribute('data-situacao') || '';
                const valor = row.getAttribute('data-valor') || '';

                // Captura data de geração da coluna td-data
                const tdData = row.querySelector('.td-data');
                const data = tdData ? tdData.innerText.trim() : '';

                // Captura competência da coluna td-competencia
                const tdComp = row.querySelector('.td-competencia');
                const competencia = tdComp ? tdComp.innerText.trim() : '';

                // Captura nome do tomador da coluna td-texto-grande
                const tdTomador = row.querySelector('.td-texto-grande');
                const tomador = tdTomador ? tdTomador.innerText.trim().substring(0, 60) : '';

                // Busca chave numérica de 44+ dígitos no HTML da linha
                // usada para montar a URL de download direta
                const htmlRow = row.innerHTML;
                const matchChave = htmlRow.match(/Download\/NFSe\/([0-9]{40,60})/);
                const chaveNumerica = matchChave ? matchChave[1] : null;

                // Busca link de download XML no menu de opções da linha
                const links = Array.from(row.querySelectorAll('a'));
                const linkDownload = links.find(a =>
                    (a.href && a.href.includes('Download')) ||
                    a.innerText.includes('XML') ||
                    a.innerText.includes('Download')
                );
                const urlDownloadLink = linkDownload ? linkDownload.href : null;

                return {
                    data_chave: chaveEncoded,
                    chave_acesso: chaveNumerica,
                    situacao: situacao,
                    valor: valor,
                    data: data,
                    competencia: competencia,
                    tomador: tomador,
                    url_download: chaveNumerica
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                        : urlDownloadLink
                };
            });
        }""")

        print(f"Notas encontradas: {len(notas_raw)}")
        for n in notas_raw:
            print(f"  {n['data']} — {n['tomador']} — situacao: {n['situacao']} — chave: {n['data_chave'][-20:] if n['data_chave'] else 'N/A'}")

        return notas_raw

    except Exception as e:
        # Salva screenshot para debug em caso de erro
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")
        print(f"Baixando nota ...{str(chave)[-10:]}...")

        if not url:
            # Se não tem URL direta tenta montar via data-chave encoded
            data_chave = nota.get("data_chave")
            if data_chave:
                # Tenta acessar a página de opções e clicar no menu de download
                print("Tentando download via menu de opções...")
                try:
                    # Busca o link de download pelo data-chave na tabela
                    link = page.locator(
                        f"tr[data-chave='{data_chave}'] a.icone-trigger"
                    ).first
                    link.click()
                    page.wait_for_timeout(1000)

                    # Clica em Download XML no menu que abriu
                    btn_xml = page.locator(
                        "a:has-text('Download XML'), a:has-text('XML')"
                    ).first
                    with page.expect_download(timeout=60000) as download_info:
                        btn_xml.click()

                    caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")
                    download_info.value.save_as(caminho)
                    print(f"XML salvo via menu: {caminho}")
                    page.keyboard.press("Escape")
                    return True
                except Exception as e:
                    print(f"Falha via menu: {e}")
                    return False
            print("Sem URL de download disponível")
            return False

        # Download via URL direta — método principal
        # A URL segue o padrão: /Notas/Download/NFSe/{chave_numerica_44_digitos}
        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")
        with page.expect_download(timeout=60000) as download_info:
            page.goto(url)

        download_info.value.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
