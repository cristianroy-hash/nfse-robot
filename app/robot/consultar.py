import os
import asyncio
from datetime import datetime

print("🔥 consultar.py carregado")

CERT_PATH = "/app/certificado.pfx"
CERT_PASSWORD = "SENHA_DO_CERT"


async def criar_contexto_com_certificado(browser):
    with open(CERT_PATH, "rb") as f:
        cert_bytes = f.read()

    context = await browser.new_context(
        ignore_https_errors=True,
        client_certificates=[{
            "origin": "https://www.nfse.gov.br",
            "pfx": cert_bytes,
            "passphrase": CERT_PASSWORD
        }]
    )

    return context


async def consultar_notas(page, data_inicio, data_fim):
    print("📄 Iniciando consulta...")

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

    print("URL:", page.url)

    if "login" in page.url.lower():
        raise Exception("❌ Não autenticado")

    await page.wait_for_selector("#datainicio", timeout=60000)

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


async def baixar_xml(page, nota, download_dir):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        async with page.expect_download(timeout=40000) as download_info:
            await page.evaluate(f"window.open('{url}', '_blank')")

        download = await download_info.value
        await download.save_as(caminho)

        print(f"✅ XML: {chave}")
        return True

    except Exception as e:
        print("Erro download:", str(e))
        return False
