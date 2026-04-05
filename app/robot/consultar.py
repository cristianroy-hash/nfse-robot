import os
import re
import asyncio
from datetime import datetime

# 1. Adicionamos 'async' antes de 'def'
async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Converte formato YYYY-MM-DD para DD/MM/YYYY que o portal espera
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        # Navega direto para a página de notas emitidas
        # ADICIONADO: await
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        # ADICIONADO: await
        await page.wait_for_timeout(3000)

        # Preenche data inicial
        print("Preenchendo data inicial...")
        # ADICIONADO: wait_for_selector para garantir que o campo carregou
        await page.wait_for_selector("#datainicio", timeout=30000)
        campo_ini = page.locator("#datainicio")
        
        # ADICIONADO: await em todas as interações
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_ini_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        # Preenche data final
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_fim_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        # Verifica se os valores foram preenchidos (await adicionado)
        val_ini = await page.locator("#datainicio").input_value()
        val_fim = await page.locator("#datafim").input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # Clica no botão Filtrar (await adicionado)
        print("Clicando em Filtrar...")
        await page.locator("button:has-text('Filtrar')").first.click()
        await page.wait_for_timeout(6000)

        # Captura notas usando evaluate (await adicionado)
        notas_raw = await page.evaluate("""() => {
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

        print(f"Notas encontradas: {len(notas_raw)}")
        return notas_raw

    except Exception as e:
        # await adicionado no screenshot
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or "nota"
        
        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        # ADICIONADO: async with para o expect_download
        try:
            async with page.expect_download(timeout=60000) as download_info:
                # ADICIONADO: await
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)
            print(f"XML salvo: {caminho}")
            return True

        except Exception:
            # Fallback Fetch (ADICIONADO: await)
            print("Tentando download via fetch...")
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{
                    credentials: 'include',
                    headers: {{ 'Accept': 'application/xml, text/xml, */*' }}
                }});
                return await r.text();
            }}""")

            if conteudo and len(conteudo) > 100:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True
            return False

    except Exception as e:
        print(f"Erro ao baixar nota: {str(e)}")
        return False
