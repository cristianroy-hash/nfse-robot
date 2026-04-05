import os
import re
import asyncio
from datetime import datetime

async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Iniciando consulta: {data_inicio} a {data_fim}")

        # Formatação de datas
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        
        # Navega para a página de Notas Emitidas
        # Adicionado wait_until="load" para garantir que o DOM esteja pronto
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="load",
            timeout=90000
        )
        
        # Espera extra para garantir que os scripts de data carreguem
        await page.wait_for_timeout(5000)

        # Preenchimento da Data Inicial
        print("Preenchendo data inicial...")
        await page.wait_for_selector("#datainicio", timeout=30000)
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_ini_fmt, delay=100)
        await page.keyboard.press("Tab")

        # Preenchimento da Data Final
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_fim_fmt, delay=100)
        await page.keyboard.press("Tab")

        # Clique no Filtro
        print("Clicando em Filtrar...")
        # Usando um seletor mais específico para o botão de filtrar
        btn_filtrar = page.locator("button.btn-primary:has-text('Filtrar')").first
        await btn_filtrar.click()
        
        # Espera o carregamento dos resultados
        await page.wait_for_timeout(8000)

        notas_acumuladas = []
        pagina_atual = 1

        while True:
            print(f"--- Processando Página {pagina_atual} ---")
            
            # Captura as notas usando o evaluate (sua lógica original mantida)
            notas_pagina = await page.evaluate("""() => {
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
                        a.innerText.includes('XML')
                    );

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
                            : (linkDownload ? linkDownload.href : null)
                    };
                });
            }""")

            notas_acumuladas.extend(notas_pagina)
            print(f"Página {pagina_atual}: {len(notas_pagina)} notas encontradas.")

            # Lógica de Paginação
            # Procuramos o botão de "Próximo" na lista de paginação
            btn_proximo_li = page.locator("ul.pagination li").filter(has_text=re.compile(r"^\s*>\s*$"))
            
            if await btn_proximo_li.count() > 0:
                classe_li = await btn_proximo_li.evaluate("el => el.className")
                if "disabled" in classe_li:
                    print("Última página alcançada.")
                    break
                else:
                    print("Indo para a próxima página...")
                    await btn_proximo_li.locator("a").click()
                    # Espera carregar a nova página
                    await page.wait_for_timeout(6000)
                    pagina_atual += 1
            else:
                print("Botão de próxima página não localizado. Encerrando.")
                break

        return notas_acumuladas

    except Exception as e:
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or re.sub(r'[^a-zA-Z0-9]', '', str(chave))[:30]

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        try:
            # Tenta via download oficial do Playwright
            async with page.expect_download(timeout=45000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            
            download = await download_info.value
            await download.save_as(caminho)
            print(f"XML salvo: {caminho}")
            return True
        except Exception:
            # Fallback Fetch em caso de falha no popup
            print(f"Tentando download via fetch para {nome_arquivo}...")
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")

            if conteudo and "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True
        return False
    except Exception as e:
        print(f"Erro ao baixar nota {nome_arquivo}: {str(e)}")
        return False
