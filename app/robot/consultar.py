import os
import asyncio
from datetime import datetime

# =========================
# CONSULTA DE NOTAS
# =========================
async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Iniciando consulta: {data_inicio} até {data_fim}")

        # =========================
        # FORMATAR DATAS
        # =========================
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

        # =========================
        # NAVEGAÇÃO ROBUSTA
        # =========================
        print("Acessando página de notas...")
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",  # 🔥 mais confiável que domcontentloaded
            timeout=90000
        )

        # Espera extra (portal gov é lento mesmo)
        await page.wait_for_timeout(5000)

        print("URL atual:", page.url)

        # =========================
        # VALIDA SE ESTÁ LOGADO
        # =========================
        if "login" in page.url.lower():
            await page.screenshot(path="/tmp/erro_login.png")
            raise Exception("Sessão não autenticada (redirecionado para login)")

        # =========================
        # ESPERA CAMPO (COM DEBUG)
        # =========================
        try:
            await page.wait_for_selector("#datainicio", timeout=60000)
        except:
            print("❌ Campo #datainicio NÃO encontrado")

            html = await page.content()
            print("Tem datainicio no HTML?", "#datainicio" in html)

            await page.screenshot(path="/tmp/erro_sem_campo.png")

            raise Exception("Campo de data não apareceu — possível erro de carregamento ou login")

        # Pequena pausa para JS interno estabilizar
        await asyncio.sleep(2)

        # =========================
        # PREENCHIMENTO
        # =========================
        print("Preenchendo datas...")

        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_ini_fmt, delay=80)
        await page.keyboard.press("Tab")

        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=80)
        await page.keyboard.press("Tab")

        # Validação
        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()
        print(f"Datas preenchidas: {val_ini} até {val_fim}")

        # =========================
        # FILTRAR
        # =========================
        print("Clicando em Filtrar...")
        await page.locator("button:has-text('Filtrar')").first.click(force=True)

        # Espera carregar resultados
        await page.wait_for_timeout(8000)

        # =========================
        # EXTRAÇÃO
        # =========================
        print("Extraindo notas...")

        notas_raw = await page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-chave]');
            return Array.from(rows).map(row => {
                const chaveEncoded = row.getAttribute('data-chave');
                const htmlRow = row.innerHTML;

                const matchChave = htmlRow.match(/Download\\/NFSe\\/([0-9]{40,60})/);
                const chaveNumerica = matchChave ? matchChave[1] : null;

                return {
                    data_chave: chaveEncoded,
                    chave_acesso: chaveNumerica,
                    situacao: row.getAttribute('data-situacao') || '',
                    valor: row.getAttribute('data-valor') || '',
                    data: row.querySelector('.td-data')?.innerText.trim() || '',
                    competencia: row.querySelector('.td-competencia')?.innerText.trim() || '',
                    tomador: row.querySelector('.td-texto-grande')?.innerText.trim().substring(0, 60) || '',
                    url_download: chaveNumerica
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                        : null
                };
            });
        }""")

        print(f"✅ {len(notas_raw)} notas encontradas")

        if len(notas_raw) == 0:
            await page.screenshot(path="/tmp/sem_notas.png")
            print("⚠️ Nenhuma nota encontrada — verificar filtro ou sessão")

        return notas_raw

    except Exception as e:
        print(f"❌ ERRO na consulta: {str(e)}")
        await page.screenshot(path="/tmp/erro_geral_consulta.png")
        raise


# =========================
# DOWNLOAD XML
# =========================
async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            print("Nota sem URL")
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        print(f"⬇️ Baixando {str(chave)[-10:]}")

        # =========================
        # MÉTODO 1: DOWNLOAD NATIVO
        # =========================
        try:
            async with page.expect_download(timeout=40000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)

            print("✅ Download via navegador OK")
            return True

        except Exception as e:
            print("⚠️ Falha no download direto:", str(e))

        # =========================
        # MÉTODO 2: FETCH (fallback)
        # =========================
        try:
            print("Tentando via fetch...")

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

                print("✅ Download via fetch OK")
                return True

        except Exception as e:
            print("❌ Fetch falhou:", str(e))

        return False

    except Exception as e:
        print(f"❌ Erro geral ao baixar XML: {str(e)}")
        return False
