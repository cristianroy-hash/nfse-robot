import os
import re
import base64
from datetime import datetime

async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")
        print("Navegando para o portal de Notas Emitidas...")
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=90000
        )
        await page.wait_for_timeout(5000)

        # =========================
        # VALIDA LOGIN
        # =========================
        if await page.locator("#datainicio").count() == 0:
            print(f"Campo #datainicio não encontrado. URL atual: {page.url}")
            if "Login" in page.url:
                btn_cert = page.locator("a[href*='Certificado'], button:has-text('Certificado')").first
                if await btn_cert.count() > 0:
                    print("Na tela de login. Clicando no botão Certificado...")
                    await btn_cert.click()
                    await page.wait_for_timeout(8000)
                    await page.goto(
                        "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
                        wait_until="networkidle"
                    )
                else:
                    raise Exception("❌ Não foi possível realizar o login via Certificado.")

        print("Aguardando campo de data inicial aparecer...")
        campo_ini = page.locator("#datainicio")
        await campo_ini.wait_for(state="visible", timeout=30000)

        # =========================
        # FILTRO
        # =========================
        print("Preenchendo data inicial...")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_ini_fmt, delay=100)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(800)

        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=100)
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(800)

        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        print("Clicando em Filtrar...")
        await page.locator("button:has-text('Filtrar')").first.click()
        await page.wait_for_timeout(8000)

        # =========================
        # PAGINAÇÃO ROBUSTA (MANTIDA)
        # =========================
        todas_notas = []
        pagina = 1
        chaves_vistas = set()
        MAX_PAGINAS = 50

        while True:
            print(f"📄 Lendo página {pagina}...")

            if pagina > MAX_PAGINAS:
                print("🚫 Paginação interrompida (limite de segurança atingido)")
                break

            await page.wait_for_selector("body", timeout=15000)

            texto_pagina = await page.content()
            if "Nenhum registro encontrado" in texto_pagina:
                print("🚫 Paginação finalizada")
                break

            await page.wait_for_selector("table tbody tr[data-chave]", timeout=15000)

            notas_raw = await page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr[data-chave]');
                return Array.from(rows).map(row => {
                    const chaveEncoded = row.getAttribute('data-chave');
                    const htmlRow = row.innerHTML;
                    const matchChave = htmlRow.match(/Download\\/NFSe\\/([0-9]+)/);
                    const chaveNumerica = matchChave ? matchChave[1] : null;
                    return {
                        data_chave: chaveEncoded,
                        chave_acesso: chaveNumerica,
                        url_download: chaveNumerica
                            ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                            : null
                    };
                });
            }""")

            if not notas_raw:
                break

            novas_notas = []
            for nota in notas_raw:
                chave = nota.get("chave_acesso") or nota.get("data_chave")
                if chave not in chaves_vistas:
                    chaves_vistas.add(chave)

                    # ✅ ADIÇÃO SEGURA DO DANFSE (NÃO QUEBRA XML)
                    nota["url_danfse"] = (
                        "https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave="
                        + nota["data_chave"]
                    ) if nota.get("data_chave") else None

                    novas_notas.append(nota)

            if not novas_notas:
                print("🚫 Paginação finalizada (duplicados)")
                break

            todas_notas.extend(novas_notas)
            print(f"Notas acumuladas: {len(todas_notas)}")

            # =========================
            # DETECÇÃO UNIVERSAL DE PRÓXIMA PÁGINA (MANTIDA)
            # =========================
            print("Verificando próxima página...")
            proxima_num = str(pagina + 1)

            botao_num = page.locator(f"ul.pagination li a:text-is('{proxima_num}')").first
            botao_next = page.locator(
                "ul.pagination li a[rel='next'], ul.pagination li a:has-text('>')"
            ).first

            target_button = None
            if await botao_num.count() > 0:
                target_button = botao_num
            elif await botao_next.count() > 0:
                target_button = botao_next

            # =========================
            # FALLBACK INTELIGENTE (MANTIDO)
            # =========================
            if not target_button or await target_button.count() == 0:
                pagina += 1
                url = f"https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas?pg={pagina}"
                print(f"➡️ Fallback página {pagina}")
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(5000)
                continue

            await target_button.click()
            await page.wait_for_timeout(9000)
            pagina += 1

        print(f"✅ Total final de notas: {len(todas_notas)}")
        return todas_notas

    except Exception as e:
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


# =========================
# CORREÇÃO CRÍTICA DO XML
# =========================
async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        nome = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome}.xml")

        context = page.context
        new_page = await context.new_page()

        try:
            async with new_page.expect_download(timeout=30000) as download_info:
                await new_page.goto(url)
            download = await download_info.value
            await download.save_as(caminho)
            await new_page.close()
            return True
        except:
            await new_page.close()

            # fallback original mantido
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")

            if conteudo and "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True

        return False
    except:
        return False


# =========================
# GARANTE EXPORT DO DANFSE (FIX DO CRASH)
# =========================
async def baixar_danfse(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_danfse")
        nome = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome}.pdf")

        context = page.context
        new_page = await context.new_page()

        try:
            async with new_page.expect_download(timeout=30000) as download_info:
                await new_page.goto(url)
            download = await download_info.value
            await download.save_as(caminho)
            await new_page.close()
            return True
        except:
            await new_page.close()
        return False
    except:
        return False
