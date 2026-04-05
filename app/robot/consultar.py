import os
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

CERT_PATH = "/app/certificado.pfx"   # caminho no Railway
CERT_PASSWORD = "SENHA_DO_CERT"

# =========================
# LOGIN COM CERTIFICADO REAL
# =========================
async def criar_contexto_com_certificado(browser):
    context = await browser.new_context(
        ignore_https_errors=True,

        # 🔥 ESSENCIAL: certificado cliente
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "pfxPath": CERT_PATH,
            "passphrase": CERT_PASSWORD
        }]
    )

    return context


async def realizar_login(page):
    print("🔐 Acessando portal com certificado...")

    await page.goto(
        "https://www.nfse.gov.br/EmissorNacional",
        wait_until="networkidle",
        timeout=90000
    )

    await page.wait_for_timeout(8000)

    print("URL após acesso:", page.url)

    # Se ainda estiver em login → falhou
    if "login" in page.url.lower():
        await page.screenshot(path="/tmp/erro_login.png")
        raise Exception("❌ Certificado não autenticou corretamente")

    print("✅ Login via certificado OK")


# =========================
# CONSULTA
# =========================
async def consultar_notas(page, data_inicio, data_fim):
    print(f"📄 Consultando: {data_inicio} até {data_fim}")

    dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
    dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")

    data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
    data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

    await page.goto(
        "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
        wait_until="networkidle",
        timeout=90000
    )

    await page.wait_for_timeout(5000)

    print("URL consulta:", page.url)

    if "login" in page.url.lower():
        raise Exception("❌ Sessão inválida — certificado não autenticou")

    await page.wait_for_selector("#datainicio", timeout=60000)

    # Preenche datas
    await page.fill("#datainicio", data_ini_fmt)
    await page.fill("#datafim", data_fim_fmt)

    await page.click("button:has-text('Filtrar')")

    await page.wait_for_timeout(8000)

    notas = await page.evaluate("""() => {
        const rows = document.querySelectorAll('table tbody tr[data-chave]');
        return Array.from(rows).map(row => {
            const html = row.innerHTML;
            const match = html.match(/Download\\/NFSe\\/([0-9]{40,60})/);
            const chave = match ? match[1] : null;

            return {
                chave_acesso: chave,
                url_download: chave
                    ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chave
                    : null
            };
        });
    }""")

    print(f"✅ {len(notas)} notas")
    return notas


# =========================
# MAIN
# =========================
async def executar_fluxo(data_inicio, data_fim):
    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        # 🔥 AQUI ESTÁ A CORREÇÃO REAL
        context = await criar_contexto_com_certificado(browser)

        page = await context.new_page()

        try:
            await realizar_login(page)

            cookies = await context.cookies()
            print("🍪 Cookies:", len(cookies))

            notas = await consultar_notas(page, data_inicio, data_fim)

            print("🚀 Finalizado")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(executar_fluxo("2026-03-01", "2026-03-31"))
