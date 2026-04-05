import os
import re
from datetime import datetime

# Adicionamos 'async' antes de 'def'
async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        await page.wait_for_timeout(3000)

        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_ini_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_fim_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        print("Clicando em Filtrar...")
        await page.locator("button:has-text('Filtrar')").first.click()
        await page.wait_for_timeout(6000)

        notas_acumuladas = []
        pagina_atual = 1

        while True:
            print(f"--- Processando Página {pagina_atual} ---")
            
            # Captura notas da página atual
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

            # Lógica de Paginação corrigida com await
            btn_proximo_li = page.locator("ul.pagination li").filter(has_text=re.compile(r"^\s*>\s*$"))
            
            if await btn_proximo_li.count() > 0:
                classe_li = await btn_proximo_li.evaluate("el => el.className")
                if "disabled" in classe_li:
                    print("Última página alcançada.")
                    break
                else:
                    print("Indo para a próxima página...")
                    await btn_proximo_li.locator("a").click()
                    await page.wait_for_timeout(5000)
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
            async with page.expect_download(timeout=60000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            
            download = await download_info.value
            await download.save_as(caminho)
            print(f"XML salvo: {caminho}")
            return True
        except Exception:
            # Fallback Fetch
            print("Tentando download via fetch...")
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
        print(f"Erro ao baixar nota: {str(e)}")
        return False
