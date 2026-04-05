import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

# =========================
# LOGIN REAL NO PORTAL
# =========================
async def realizar_login(page):
    print("🔐 Iniciando login no portal...")

    await page.goto(
        "https://www.nfse.gov.br/EmissorNacional",
        wait_until="networkidle",
        timeout=90000
    )

    await page.wait_for_timeout(5000)

    print("URL inicial:", page.url)

    # ⚠️ IMPORTANTE:
    # Aqui você deve ajustar conforme o botão real do portal
    # (texto pode variar um pouco)

    try:
        print("Clicando em login com certificado...")
        await page.click("text=Certificado", timeout=15000)
    except:
        print("⚠️ Botão de certificado não encontrado (pode já estar logado)")

    # Espera navegação pós-login
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(8000)

    print("URL após tentativa de login:", page.url)

    # =========================
    # VALIDA LOGIN REAL
    # =========================
    if "login" in page.url.lower():
        await page.screenshot(path="/tmp/erro_login.png")
        raise Exception("❌ Login NÃO foi concluído (ainda está na tela de login)")

    print("✅ Login confirmado")


# =========================
# CONSULTA
# =========================
async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"📄 Consultando notas: {data_inicio} até {data_fim}")

        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

        # 🔥 IMPORTANTE: usar mesma sessão (não recriar page)
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=90000
        )

        await page.wait_for_timeout(5000)

        print("URL consulta:", page.url)

        if "login" in page.url.lower():
            raise Exception("❌ Sessão perdida antes da consulta")

        # Espera campo
        await page.wait_for_selector("#datainicio", timeout=60000)

        await asyncio.sleep(2)

        # Preenche datas
        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_ini_fmt, delay=80)

        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(data_fim_fmt, delay=80)

        print("🔎 Aplicando filtro...")
        await page.locator("button:has-text('Filtrar')").click(force=True)

        await page.wait_for_timeout(8000)

        notas = await page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-chave]');
            return Array.from(rows).map(row => {
                const htmlRow = row.innerHTML;
                const match = htmlRow.match(/Download\\/NFSe\\/([0-9]{40,60})/);
                const chave = match ? match[1] : null;

                return {
                    chave_acesso: chave,
                    url_download: chave
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chave
                        : null
                };
            });
        }""")

        print(f"✅ {len(notas)} notas encontradas")
        return notas

    except Exception as e:
        print("❌ Erro na consulta:", str(e))
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise


# =========================
# DOWNLOAD
# =========================
async def baixar_xml(page, nota, download_dir):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        try:
            async with page.expect_download(timeout=40000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)

            print(f"✅ XML salvo: {chave}")
            return True

        except:
            # fallback fetch
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")

            if "<?xml" in conteudo:
                with open(caminho, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                print(f"✅ XML via fetch: {chave}")
                return True

        return False

    except Exception as e:
        print("Erro download:", str(e))
        return False


# =========================
# FLUXO PRINCIPAL (IMPORTANTE)
# =========================
async def executar_fluxo(data_inicio, data_fim):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  # Railway precisa ser True
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        # 🔥 CONTEXTO ÚNICO (ESSENCIAL)
        context = await browser.new_context()

        # 🔥 PAGE ÚNICA (ESSENCIAL)
        page = await context.new_page()

        try:
            # LOGIN
            await realizar_login(page)

            # VALIDA COOKIE (debug forte)
            cookies = await context.cookies()
            print("🍪 Cookies ativos:", len(cookies))

            # CONSULTA
            notas = await consultar_notas(page, data_inicio, data_fim)

            # DOWNLOAD
            download_dir = "/tmp/xmls"
            os.makedirs(download_dir, exist_ok=True)

            for nota in notas[:15]:
                await baixar_xml(page, nota, download_dir)

            print("🚀 Processo finalizado com sucesso")

        finally:
            await browser.close()


# =========================
# EXECUÇÃO LOCAL (TESTE)
# =========================
if __name__ == "__main__":
    asyncio.run(executar_fluxo("2026-03-01", "2026-03-31"))
