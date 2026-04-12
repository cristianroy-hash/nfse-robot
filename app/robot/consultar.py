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
        # PAGINAÇÃO ROBUSTA
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
            if "Nenhum registro encontrado" in texto_pagina or "Nenhum registro" in texto_pagina:
                print("🚫 Paginação finalizada (mensagem do portal)")
                break

            await page.wait_for_selector("table tbody tr[data-chave]", timeout=15000)

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

            novas_notas = []
            for nota in notas_raw:
                chave = nota.get("chave_acesso") or nota.get("data_chave")
                if chave not in chaves_vistas:
                    chaves_vistas.add(chave)

                    # ✅ ADIÇÃO DO DANFSE SEM QUEBRAR NADA
                    nota["url_danfse"] = (
                        "https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave="
                        + nota["data_chave"]
                    ) if nota.get("data_chave") else None

                    # =========================
                    # ✅ NOVA MELHORIA — CONTEÚDO XML EM BASE64
                    # Baixa o XML da nota via fetch autenticado e retorna
                    # o conteúdo em base64 para o frontend poder fazer
                    # o download sem depender de URL autenticada que expira.
                    # =========================
                    try:
                        url_xml = nota.get("url_download")
                        if url_xml:
                            conteudo_xml = await page.evaluate(f"""async () => {{
                                try {{
                                    const r = await fetch('{url_xml}', {{ credentials: 'include' }});
                                    return await r.text();
                                }} catch(e) {{ return null; }}
                            }}""")
                            if conteudo_xml and "<?xml" in conteudo_xml:
                                nota["conteudo_xml"] = conteudo_xml
                                print(f"✅ XML capturado: {chave[:20]}...")
                            else:
                                nota["conteudo_xml"] = None
                        else:
                            nota["conteudo_xml"] = None
                    except Exception as e_xml:
                        print(f"⚠ Erro ao capturar XML: {e_xml}")
                        nota["conteudo_xml"] = None
                    # =========================
                    # FIM NOVA MELHORIA XML
                    # =========================

                    # =========================
                    # ✅ NOVA MELHORIA — CONTEÚDO DANFSE EM BASE64
                    # Baixa o PDF do DANFSe via sessão autenticada do browser
                    # e retorna o conteúdo em base64 para o frontend poder
                    # gerar o ZIP sem bloqueio de CORS.
                    # =========================
                    try:
                        url_danfse = nota.get("url_danfse")
                        if url_danfse:
                            context = page.context
                            new_page = await context.new_page()
                            conteudo_danfse_b64 = None
                            try:
                                async with new_page.expect_download(timeout=20000) as download_info:
                                    await new_page.goto(url_danfse)
                                download = await download_info.value

                                # Salva em memória e converte para base64
                                import tempfile
                                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                                    tmp_path = tmp.name
                                await download.save_as(tmp_path)

                                with open(tmp_path, "rb") as f:
                                    conteudo_danfse_b64 = base64.b64encode(f.read()).decode("utf-8")
                                os.remove(tmp_path)
                                print(f"✅ DANFSe capturado em base64: {chave[:20]}...")

                            except Exception as e_dl:
                                print(f"⚠ Falha ao baixar DANFSe via download: {e_dl}")
                            finally:
                                await new_page.close()

                            nota["conteudo_danfse"] = conteudo_danfse_b64
                        else:
                            nota["conteudo_danfse"] = None
                    except Exception as e_danfse:
                        print(f"⚠ Erro ao capturar DANFSe: {e_danfse}")
                        nota["conteudo_danfse"] = None
                    # =========================
                    # FIM NOVA MELHORIA DANFSE
                    # =========================

                    novas_notas.append(nota)

            if not novas_notas:
                print("🚫 Paginação finalizada (dados duplicados detectados)")
                break

            todas_notas.extend(novas_notas)
            print(f"Notas acumuladas: {len(todas_notas)}")

            # =========================
            # DETECÇÃO UNIVERSAL DE PRÓXIMA PÁGINA
            # =========================
            print("Verificando próxima página...")

            proxima_num = str(pagina + 1)
            botao_num = page.locator(f"ul.pagination li a:text-is('{proxima_num}')").first

            botao_next = page.locator(
                "ul.pagination li a[rel='next'], ul.pagination li a:has-text('>'), ul.pagination li a:has-text('›'), ul.pagination li a:has-text('»')"
            ).first

            target_button = None

            if await botao_num.count() > 0:
                print(f"➡️ Indo para página {proxima_num}")
                target_button = botao_num
            elif await botao_next.count() > 0:
                print("➡️ Indo para próxima via botão '>'")
                target_button = botao_next

            # =========================
            # FALLBACK INTELIGENTE
            # =========================
            if not target_button or await target_button.count() == 0:
                proxima_pagina = pagina + 1
                url_forcada = f"https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas?pg={proxima_pagina}&datainicio={data_ini_fmt}&datafim={data_fim_fmt}"

                print(f"➡️ [FALLBACK] Forçando navegação para página {proxima_pagina}")

                await page.goto(url_forcada, wait_until="networkidle")
                await page.wait_for_timeout(5000)

                texto_forcado = await page.content()
                if "Nenhum registro encontrado" in texto_forcado or "Nenhum registro" in texto_forcado:
                    print("🚫 Paginação finalizada (fallback sem registros)")
                    break

                pagina = proxima_pagina
                continue

            is_disabled = await target_button.evaluate("""el => {
                const li = el.closest('li');
                return li && li.classList.contains('disabled');
            }""")

            if is_disabled:
                print("🚫 Botão próximo desabilitado")
                break

            await target_button.click()
            await page.wait_for_timeout(9000)

            pagina += 1

        print(f"✅ Total final de notas: {len(todas_notas)}")
        return todas_notas

    except Exception as e:
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


# =========================
# CORREÇÃO DO DOWNLOAD XML
# =========================
async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

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

            conteudo = await page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('{url}', {{ credentials: 'include' }});
                    return await r.text();
                }} catch(e) {{ return null; }}
            }}""")

            if conteudo and "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)
                return True

        return False

    except:
        return False


# =========================
# NOVO: DOWNLOAD DANFSE (CORRIGE CRASH)
# =========================
async def baixar_danfse(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_danfse")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.pdf")

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
