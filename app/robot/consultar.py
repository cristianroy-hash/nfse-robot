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
                    // Regex flexível para capturar o ID numérico do XML no link de download
                    const matchChave = htmlRow.match(/Download\/NFSe\/([0-9]+)/);
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

            # evita duplicação (BUG DO PORTAL)
            novas_notas = []
            for nota in notas_raw:
                chave = nota.get("chave_acesso") or nota.get("data_chave")
                if chave not in chaves_vistas:
                    chaves_vistas.add(chave)
                    # NOVO: monta URL do DANFSe oficial via portal público
                    # O data_chave já capturado na listagem é o token que o portal público usa
                    nota["url_danfse"] = (
                        "https://www.nfse.gov.br/ConsultaPublica/Download/DANFSe?chave="
                        + nota["data_chave"]
                    ) if nota.get("data_chave") else None
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
        url = nota.get("url_download")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            print(f"⚠️ Sem URL de download para {nome_arquivo}")
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            download = await download_info.value
            await download.save_as(caminho)
            return True
        except:
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
# NOVO: DOWNLOAD DO DANFSe OFICIAL VIA PORTAL PÚBLICO
# =========================
async def baixar_danfse(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_danfse")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            print(f"⚠️ url_danfse não disponível para {chave}")
            return False

        caminho = os.path.join(download_dir, f"{chave}.pdf")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")
            download = await download_info.value
            await download.save_as(caminho)
            return True
        except Exception:
            # Fallback fetch b64 para PDF
            conteudo_b64 = await page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('{url}');
                    if (!r.ok) return null;
                    const buf = await r.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let bin = '';
                    bytes.forEach(b => bin += String.fromCharCode(b));
                    return window.btoa(bin);
                }} catch(e) {{ return null; }}
            }}""")

            if conteudo_b64:
                dados = base64.b64decode(conteudo_b64)
                if dados[:4] == b'%PDF':
                    with open(caminho, 'wb') as f:
                        f.write(dados)
                    return True
        return False
    except Exception:
        return False


# =========================
# NOVO: DOWNLOAD EM LOTE — XML (ZIP)
# =========================
async def baixar_lote_xml(page, notas: list, download_dir: str):
    os.makedirs(download_dir, exist_ok=True)
    sucesso, falha, arquivos = 0, 0, []

    for i, nota in enumerate(notas):
        chave = nota.get("chave_acesso") or nota.get("data_chave", f"nota_{i}")
        ok = await baixar_xml(page, nota, download_dir)
        if ok:
            sucesso += 1
            arquivos.append(os.path.join(download_dir, f"{chave}.xml"))
        else:
            falha += 1
        await page.wait_for_timeout(1000)

    return {"sucesso": sucesso, "falha": falha, "arquivos": arquivos}


# =========================
# NOVO: DOWNLOAD EM LOTE — DANFSe PDF (ZIP)
# =========================
async def baixar_lote_danfse(page, notas: list, download_dir: str):
    os.makedirs(download_dir, exist_ok=True)
    sucesso, falha, arquivos = 0, 0, []

    for i, nota in enumerate(notas):
        chave = nota.get("chave_acesso") or nota.get("data_chave", f"nota_{i}")
        ok = await baixar_danfse(page, nota, download_dir)
        if ok:
            sucesso += 1
            arquivos.append(os.path.join(download_dir, f"{chave}.pdf"))
        else:
            falha += 1
        await page.wait_for_timeout(1000)

    return {"sucesso": sucesso, "falha": falha, "arquivos": arquivos}
