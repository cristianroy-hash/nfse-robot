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

        # controle de duplicidade
        chaves_vistas = set()

        # limite de segurança contra loop infinito
        MAX_PAGINAS = 50

        while True:
            print(f"📄 Lendo página {pagina}...")

            # fail-safe
            if pagina > MAX_PAGINAS:
                print("🚫 Paginação interrompida (limite de segurança atingido)")
                break

            await page.wait_for_selector("body", timeout=15000)

            # valida página vazia (MAIS ROBUSTO)
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
                        url_download_xml: chaveNumerica ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica : null,
                        url_download_pdf: chaveNumerica ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Visualizar/' + chaveNumerica : null
                    };
                });
            }""")

            if not notas_raw:
                print("Nenhuma nota encontrada nesta página.")
                break

            # evita duplicação (BUG DO PORTAL)
            novas_notas = []
            for nota in notas_raw:
                chave = nota.get("chave_acesso") or nota.get("data_chave")
                if chave not in chaves_vistas:
                    chaves_vistas.add(chave)
                    
                    # 🔥 NOVO: Captura de XML (Essencial para a alternativa de conversão)
                    print(f"📥 Capturando XML da nota {chave}...")
                    nota["conteudo_xml"] = await capturar_texto_xml_silencioso(page, nota["url_download_xml"])
                    
                    # 🔥 NOVO: Captura de PDF com "Retry" em caso de erro 404
                    print(f"📥 Capturando PDF da nota {chave}...")
                    nota["conteudo_pdf_base64"] = await capturar_pdf_blindado(page, chave)
                    
                    novas_notas.append(nota)

            # parada se só vier duplicado
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

                # valida vazio no fallback
                texto_forcado = await page.content()
                if "Nenhum registro encontrado" in texto_forcado or "Nenhum registro" in texto_forcado:
                    print("🚫 Paginação finalizada (fallback sem registros)")
                    break

                pagina = proxima_pagina
                continue

            # fluxo original mantido
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


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download_xml")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)
            return True

        except:
            # Reintegrado exatamente como o original enviado
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
# 🔥 NOVO: AUXILIARES DE CAPTURA
# =========================

async def capturar_texto_xml_silencioso(page, url):
    """ NOVO: Obtém o conteúdo XML sem disparar download visual """
    if not url: return None
    try:
        return await page.evaluate(f"""async () => {{
            try {{
                const res = await fetch('{url}', {{ credentials: 'include' }});
                const text = await res.text();
                return text.includes('<?xml') ? text : null;
            }} catch(e) {{ return null; }}
        }}""")
    except: return None

async def capturar_pdf_blindado(page, chave_acesso):
    """ NOVO: Tenta capturar o PDF via clique, com uma segunda tentativa se der erro de recurso não encontrado """
    for tentativa in range(2):
        try:
            btn_visualizar = page.locator(f"a[href*='/Visualizar/{chave_acesso}']").first
            
            if await btn_visualizar.count() > 0:
                async with page.context.expect_page() as new_page_info:
                    await btn_visualizar.click()
                
                new_page = await new_page_info.value
                await new_page.wait_for_load_state("networkidle")
                
                # Checa se caiu na página de erro 404
                conteudo = await new_page.content()
                if "The resource cannot be found" in conteudo or "Server Error" in conteudo:
                    print(f"⚠️ Erro 404 detectado na nota {chave_acesso}. Tentativa {tentativa + 1}...")
                    await new_page.close()
                    await page.wait_for_timeout(3000)
                    continue # Tenta de novo
                
                await new_page.wait_for_timeout(2000)
                pdf_bytes = await new_page.pdf(format="A4", print_background=True)
                await new_page.close()
                
                return base64.b64encode(pdf_bytes).decode('utf-8')
        except Exception as e:
            print(f"Erro na tentativa {tentativa}: {e}")
            await page.wait_for_timeout(2000)
            
    return None
