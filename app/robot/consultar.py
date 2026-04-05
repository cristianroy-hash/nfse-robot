import os
import re
import asyncio
from datetime import datetime

async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Iniciando consulta: {data_inicio} a {data_fim}")

        # 1. Formatação de datas
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        
        # 2. Navegação com espera reforçada
        print("Navegando para a página de Notas Emitidas...")
        url_consulta = "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas"
        
        # Tentamos ir para a página e esperamos a rede sossegar
        await page.goto(url_consulta, wait_until="networkidle", timeout=90000)
        
        # 3. Verificação de Segurança: Se não carregou o campo, tenta um reload
        try:
            await page.wait_for_selector("#datainicio", timeout=15000)
        except:
            print("Campo não detectado, tentando recarregar a página de consulta...")
            await page.goto(url_consulta, wait_until="load")
            await page.wait_for_selector("#datainicio", timeout=30000)

        # 4. Preenchimento da Data Inicial
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_ini_fmt, delay=100)
        await page.keyboard.press("Tab")
        await asyncio.sleep(1) # Pequena pausa entre campos

        # 5. Preenchimento da Data Final
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=100)
        await page.keyboard.press("Tab")
        await asyncio.sleep(1)

        # 6. Clique no Filtro
        print("Clicando em Filtrar...")
        # Seletor mais preciso para o botão de filtrar do sistema
        btn_filtrar = page.locator("button.btn-primary", has_text="Filtrar").first
        await btn_filtrar.click()
        
        # Espera a tabela de resultados aparecer
        print("Aguardando carregamento da tabela...")
        await page.wait_for_timeout(8000)

        notas_acumuladas = []
        pagina_atual = 1

        while True:
            print(f"--- Lendo Página {pagina_atual} ---")
            
            # Garantir que a tabela carregou antes de avaliar
            await page.wait_for_selector("table tbody", timeout=10000)
            
            # Captura as notas da página atual
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
                            : null
                    };
                });
            }""")

            notas_acumuladas.extend(notas_pagina)
            print(f"Encontradas {len(notas_pagina)} notas na página {pagina_atual}.")

            # 7. Lógica de Paginação (Botão Próximo ">")
            btn_proximo_li = page.locator("ul.pagination li").filter(has_text=re.compile(r"^\s*>\s*$"))
            
            if await btn_proximo_li.count() > 0:
                classe_li = await btn_proximo_li.evaluate("el => el.className")
                if "disabled" in classe_li:
                    print("Chegamos ao fim das páginas.")
                    break
                else:
                    print("Navegando para a próxima página...")
                    await btn_proximo_li.locator("a").click()
                    # Espera carregar a nova página (importante ser generoso no tempo aqui)
                    await page.wait_for_timeout(7000)
                    pagina_atual += 1
            else:
                print("Paginação não encontrada ou única página.")
                break

        return notas_acumuladas

    except Exception as e:
        print(f"Erro na consulta: {str(e)}")
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        
        if not url:
            print(f"Nota {chave} sem URL de download.")
            return False

        nome_arquivo = f"{chave}.xml"
        caminho = os.path.join(download_dir, nome_arquivo)

        # Download via disparador de download do Playwright
        try:
            async with page.expect_download(timeout=45000) as download_info:
                # Abrir em nova aba para disparar o download
                await page.evaluate(f"window.open('{url}', '_blank')")
            
            download = await download_info.value
            await download.save_as(caminho)
            return True
        except Exception as e:
            print(f"Falha no download padrão da nota {chave}, tentando fetch...")
            # Fallback para notas problemáticas
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
        print(f"Erro total no download: {str(e)}")
        return False
