import os
import re
from datetime import datetime


async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Converte formato YYYY-MM-DD para DD/MM/YYYY que o portal espera
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        # =========================
        # ACESSO DIRETO (Fluxo Funcional)
        # =========================
        # Navega direto para a página de notas emitidas
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        await page.wait_for_timeout(3000)

        # Preenche data inicial usando ID descoberto via diagnóstico
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_ini_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        # Preenche data final usando ID descoberto via diagnóstico
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_fim_fmt, delay=80)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)

        # Verifica se os valores foram preenchidos corretamente
        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # Clica no botão Filtrar para aplicar o período
        print("Clicando em Filtrar...")
        await page.locator("button:has-text('Filtrar')").first.click()
        await page.wait_for_timeout(6000)

        # =========================
        # CAPTURA COM PAGINAÇÃO
        # =========================
        todas_notas = []
        pagina = 1

        while True:
            print(f"📄 Lendo página {pagina}...")
            
            # Captura notas usando data-chave descoberto no diagnóstico do HTML
            notas_raw = await page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr[data-chave]');
                return Array.from(rows).map(row => {
                    const chaveEncoded = row.getAttribute('data-chave');
                    const situacao = row.getAttribute('data-situacao') || '';
                    const valor = row.getAttribute('data-valor') || '';

                    // Captura data de geração da coluna td-data
                    const tdData = row.querySelector('.td-data');
                    const data = tdData ? tdData.innerText.trim() : '';

                    // Captura nome do tomador da coluna td-texto-grande
                    const tdTomador = row.querySelector('.td-texto-grande');
                    const tomador = tdTomador ? tdTomador.innerText.trim().substring(0, 60) : '';

                    // Busca chave numérica de 44+ dígitos no HTML da linha
                    const htmlRow = row.innerHTML;
                    const matchChave = htmlRow.match(/Download\/NFSe\/([0-9]{40,60})/);
                    const chaveNumerica = matchChave ? matchChave[1] : null;

                    return {
                        data_chave: chaveEncoded,
                        chave_acesso: chaveNumerica,
                        situacao: situacao,
                        valor: valor,
                        data: data,
                        tomador: tomador,
                        url_download: chaveNumerica
                            ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                            : null
                    };
                });
            }""")

            if not notas_raw:
                print("Nenhuma nota encontrada nesta página.")
                break

            todas_notas.extend(notas_raw)
            print(f"Notas encontradas até agora: {len(todas_notas)}")

            # --- LÓGICA DE PRÓXIMA PÁGINA ---
            botao_proximo = page.locator("a[rel='next'], button:has-text('Próxima')")
            
            # Se o botão não existir ou estiver desabilitado, encerra o loop
            if await botao_proximo.count() == 0:
                break
            
            is_disabled = await botao_proximo.first.evaluate("el => el.classList.contains('disabled') || el.hasAttribute('disabled')")
            if is_disabled:
                break

            print("Avançando para a próxima página...")
            await botao_proximo.first.click()
            await page.wait_for_timeout(5000)
            pagina += 1

        print(f"✅ Total de notas capturadas: {len(todas_notas)}")
        return todas_notas

    except Exception as e:
        # Salva screenshot para debug em caso de erro
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")
        
        if not url:
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        # Tentativa 1: Download Nativo do Playwright (Assíncrono)
        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            
            download = await download_info.value
            await download.save_as(caminho)
            print(f"XML salvo: {caminho}")
            return True

        except Exception as e:
            print(f"Erro no download nativo: {str(e)}. Tentando via Fetch...")
            
            # Fallback: tenta via fetch com cookies da sessão atual
            conteudo = await page.evaluate(f"""async () => {{
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
        
        return False

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
