import os
import re
import asyncio
from datetime import datetime

async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Iniciando consulta para o período: {data_inicio} a {data_fim}")

        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

        # ESTRATÉGIA: Forçar o carregamento e esperar o corpo da página estar pronto
        print("Navegando para a página de Notas Emitidas...")
        await page.goto("https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas", 
                        wait_until="domcontentloaded", 
                        timeout=90000)
        
        # O portal às vezes faz redirecionamentos internos. 
        # Vamos esperar o seletor aparecer com um tempo maior e logar se ele aparecer.
        print("Aguardando o formulário ficar visível...")
        await page.wait_for_selector("#datainicio", state="visible", timeout=45000)
        
        # Pequena pausa física para o JavaScript do governo terminar de anexar os eventos
        await asyncio.sleep(2)

        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace") # Garante limpeza total
        await page.keyboard.type(data_ini_fmt, delay=100)
        await page.keyboard.press("Tab")

        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=100)
        await page.keyboard.press("Tab")

        # Verifica o preenchimento antes de filtrar
        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()
        print(f"Campos preenchidos: {val_ini} até {val_fim}")

        print("Clicando em Filtrar...")
        # Usamos o clique forçado caso haja algum overlay invisível
        await page.locator("button:has-text('Filtrar')").first.click(force=True)
        
        # Espera o carregamento da tabela de resultados
        print("Aguardando resultados do filtro...")
        await page.wait_for_timeout(7000)

        # Extração de dados (Igual ao seu original, mas com await)
        notas_raw = await page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-chave]');
            return Array.from(rows).map(row => {
                const chaveEncoded = row.getAttribute('data-chave');
                const htmlRow = row.innerHTML;
                const matchChave = htmlRow.match(/Download\/NFSe\/([0-9]{40,60})/);
                const chaveNumerica = matchChave ? matchChave[1] : null;

                return {
                    data_chave: chaveEncoded,
                    chave_acesso: chaveNumerica,
                    situacao: row.getAttribute('data-situacao') || '',
                    valor: row.getAttribute('data-valor') || '',
                    data: row.querySelector('.td-data')?.innerText.trim() || '',
                    tomador: row.querySelector('.td-texto-grande')?.innerText.trim().substring(0, 60) || '',
                    url_download: chaveNumerica
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                        : null
                };
            });
        }""")

        print(f"Consulta finalizada. {len(notas_raw)} notas capturadas.")
        return notas_raw

    except Exception as e:
        print(f"Falha detectada: {str(e)}")
        # Tira o print do que o robô está vendo no momento do erro
        await page.screenshot(path="/tmp/debug_tela_erro.png")
        raise Exception(f"Erro na consulta: {str(e)}")

async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "nota")
        if not url: return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        # Tentativa via Popup de Download
        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            download = await download_info.value
            await download.save_as(caminho)
            return True
        except:
            # Fallback Fetch (Executado dentro do contexto do navegador)
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")
            if "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True
        return False
    except Exception:
        return False
