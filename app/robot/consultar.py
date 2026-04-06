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

        while True:
            print(f"📄 Lendo página {pagina}...")

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

            todas_notas.extend(notas_raw)
            print(f"Notas acumuladas: {len(todas_notas)}")

            # =========================
            # 🔥 NOVA LÓGICA DEFINITIVA DE PAGINAÇÃO
            # =========================
            print("Verificando próxima página (via ícone fa-angle-right)...")

            # 🔥 NOVO: seleciona botão pelo ÍCONE (esse é o pulo do gato)
            botao_next = page.locator("ul.pagination li a:has(i.fa-angle-right)").first

            if await botao_next.count() == 0:
                print("🚫 Botão de próxima (ícone) não encontrado")
                break

            # 🔥 NOVO: verifica se está desabilitado
            is_disabled = await botao_next.evaluate("""el => {
                const li = el.closest('li');
                return li && li.classList.contains('disabled');
            }""")

            if is_disabled:
                print("🚫 Botão próxima desabilitado")
                break

            print("➡️ Clicando no botão próxima (ícone)...")
            await botao_next.click()

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
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)
            return True

        except:
            # fallback via fetch
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
