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
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        # Usa expect_download com wait_for_event para capturar o download
        # O portal retorna o arquivo como attachment — precisa esperar o evento
        with page.expect_download(timeout=60000) as download_info:
            # Abre em nova aba para não perder a sessão da página principal
            page.evaluate(f"window.open('{url}', '_blank')")

        download = download_info.value
        download.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {str(chave)[-10:]}: {str(e)}")

        # Fallback: tenta via fetch com cookies da sessão atual
        try:
            print("Tentando download via fetch...")
            conteudo = page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{
                    credentials: 'include',
                    headers: {{ 'Accept': 'application/xml, text/xml, */*' }}
                }});
                return await r.text();
            }}""")

            if conteudo and len(conteudo) > 100:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                print(f"XML salvo via fetch: {caminho}")
                return True
        except Exception as e2:
            print(f"Fallback fetch falhou: {str(e2)}")

        return False

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
