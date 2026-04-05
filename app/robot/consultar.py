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
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Preenche data inicial
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        campo_ini.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_ini_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Preenche data final
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        campo_fim.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_fim_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Clica no botão Filtrar
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(6000)

        notas_acumuladas = []
        pagina_atual = 1

        while True:
            print(f"--- Processando Página {pagina_atual} ---")
            
            # Captura notas da página atual
            notas_pagina = page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr[data-chave]');
                return Array.from(rows).map(row => {
                    const chaveEncoded = row.getAttribute('data-chave');
                    const situacao = row.getAttribute('data-situacao') || '';
                    const valor = row.getAttribute('data-valor') || '';

                    const tdData = row.querySelector('.td-data');
                    const data = tdData ? tdData.innerText.trim() : '';

                    const tdComp = row.querySelector('.td-competencia');
                    const competencia = tdComp ? tdComp.innerText.trim() : '';

                    const tdTomador = row.querySelector('.td-texto-grande');
                    const tomador = tdTomador ? tdTomador.innerText.trim().substring(0, 60) : '';

                    const htmlRow = row.innerHTML;
                    const matchChave = htmlRow.match(/Download\/NFSe\/([0-9]{40,60})/);
                    const chaveNumerica = matchChave ? matchChave[1] : null;

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

            notas_acumuladas.extend(notas_pagina)
            print(f"Página {pagina_atual}: {len(notas_pagina)} notas encontradas.")

            # Lógica de Paginação: Busca o botão ">" (Próximo)
            # O seletor busca o <li> que contém exatamente o texto ">"
            btn_proximo_li = page.locator("ul.pagination li").filter(has_text=re.compile(r"^\s*>\s*$"))
            
            if await btn_proximo_li.count() > 0:
                # Verifica se o botão está desabilitado
                classe_li = await btn_proximo_li.evaluate("el => el.className")
                if "disabled" in classe_li:
                    print("Última página alcançada.")
                    break
                else:
                    print("Indo para a próxima página...")
                    await btn_proximo_li.locator("a").click()
                    # Aguarda o carregamento AJAX da tabela
                    page.wait_for_timeout(5000)
                    pagina_atual += 1
            else:
                print("Botão de próxima página não localizado. Encerrando busca.")
                break

        print(f"Total geral de notas encontradas: {len(notas_acumuladas)}")
        for n in notas_acumuladas:
             print(f"  {n['data']} — {n['tomador']} — chave: {n['data_chave'][-20:] if n['data_chave'] else 'N/A'}")

        return notas_acumuladas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")
        
        # Limpa caracteres especiais do nome do arquivo se for Base64 (data_chave)
        if not nota.get("chave_acesso"):
            nome_arquivo = re.sub(r'[^a-zA-Z0-9]', '', str(nome_arquivo))[:30]

        print(f"Baixando nota ...{str(chave)[-10:]}...")

        if not url:
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        with page.expect_download(timeout=60000) as download_info:
            page.evaluate(f"window.open('{url}', '_blank')")

        download = download_info.value
        download.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {str(chave)[-10:]}: {str(e)}")
        
        # Fallback Fetch
        try:
            print("Tentando download via fetch...")
            conteudo = page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{
                    credentials: 'include',
                    headers: {{ 'Accept': 'application/xml, text/xml, */*' }}
                }});
                return await r.text();
            }}""")

            if conteudo and "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                print(f"XML salvo via fetch: {caminho}")
                return True
        except Exception as e2:
            print(f"Fallback fetch falhou: {str(e2)}")

        return False
