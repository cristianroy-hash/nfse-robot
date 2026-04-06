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
        # Navega para a página de notas emitidas
        print("Navegando para o portal de Notas Emitidas...")
        response = await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=90000 # Aumentado para 90s (portais gov são lentos)
        )

        # Pequena pausa para garantir o carregamento do DOM
        await page.wait_for_timeout(5000)

        # VERIFICAÇÃO DE LOGIN: Se o campo de data não existe, talvez fomos para o Login
        if await page.locator("#datainicio").count() == 0:
            print(f"Campo #datainicio não encontrado. URL atual: {page.url}")
            if "Login" in page.url:
                # Tenta forçar o clique no botão de certificado se estiver na tela de login
                btn_cert = page.locator("a[href*='Certificado'], button:has-text('Certificado')").first
                if await btn_cert.count() > 0:
                    print("Na tela de login. Clicando no botão Certificado...")
                    await btn_cert.click()
                    await page.wait_for_timeout(8000)
                    # Tenta voltar para a página de notas após o clique
                    await page.goto("https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas", wait_until="networkidle")
                else:
                    raise Exception("❌ Não foi possível realizar o login via Certificado.")

        # Espera explícita pelo seletor antes de interagir
        print("Aguardando campo de data inicial aparecer...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.wait_for(state="visible", timeout=30000)

        # Preenche data inicial
        print("Preenchendo data inicial...")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace") # Limpa garantido
        await page.keyboard.type(data_ini_fmt, delay=100)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(800)

        # Preenche data final
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=100)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(800)

        # Verifica valores preenchidos
        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # Clica no botão Filtrar
        print("Clicando em Filtrar...")
        btn_filtrar = page.locator("button:has-text('Filtrar')").first
        await btn_filtrar.click()
        
        # Espera a tabela atualizar ou o loading sumir
        await page.wait_for_timeout(8000)

        # =========================
        # CAPTURA COM PAGINAÇÃO
        # =========================
        todas_notas = []
        pagina = 1

        while True:
            print(f"📄 Lendo página {pagina}...")
            
            # Captura notas da página atual
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

            if not notas_raw:
                print("Nenhuma nota encontrada nesta página.")
                break

            todas_notas.extend(notas_raw)
            print(f"Notas capturadas: {len(todas_notas)}")

            # --- LÓGICA DE PRÓXIMA PÁGINA ---
            botao_proximo = page.locator("a[rel='next'], button:has-text('Próxima')")
            
            if await botao_proximo.count() == 0:
                break
            
            # Verifica se o botão está desabilitado
            is_disabled = await botao_proximo.first.evaluate("el => el.classList.contains('disabled') || el.hasAttribute('disabled')")
            if is_disabled:
                print("🚫 Fim da paginação (botão desabilitado).")
                break

            print("Avançando página...")
            await botao_proximo.first.click()
            await page.wait_for_timeout(6000)
            pagina += 1

        print(f"✅ Total de notas capturadas: {len(todas_notas)}")
        return todas_notas

    except Exception as e:
        print(f"❌ Erro detectado: {str(e)}")
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")
        
        if not url: return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            download = await download_info.value
            await download.save_as(caminho)
            return True
        except:
            # Fallback Fetch
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")
            if "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True
        return False
    except:
        return False
