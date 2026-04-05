import os
import re
from datetime import datetime


async def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # ... (sua formatação de datas continua igual) ...

        # =========================
        # LOGIN VIA CERTIFICADO (Ajustado)
        # =========================
        print("Acessando endpoint de autenticação por certificado...")
        
        # Tentamos ir direto para o seletor de certificado
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Login/Certificado",
            wait_until="networkidle",
            timeout=60000
        )

        await page.wait_for_timeout(5000)
        print(f"URL após tentativa de login: {page.url}")

        # Se ainda cair na tela de login, tentamos clicar no botão de certificado se ele existir
        if "Login" in page.url:
            print("Sessão não entrou direto, tentando forçar clique no botão Certificado...")
            btn_cert = page.locator("a:has-text('Certificado Digital'), button:has-text('Certificado')").first
            if await btn_cert.count() > 0:
                await btn_cert.click()
                await page.wait_for_timeout(5000)

        # VALIDAÇÃO FINAL
        if "Login" in page.url:
            await page.screenshot(path="/tmp/erro_login_detalhado.png")
            raise Exception("❌ Sessão não autenticada via Certificado")

        print("✅ Autenticação confirmada!")

        # =========================
        # IR PARA NOTAS
        # =========================
        await page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )

        await page.wait_for_timeout(3000)

        print("📅 Preenchendo datas...")

        campo_ini = page.locator("#datainicio")
        await campo_ini.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_ini_fmt, delay=80)
        await page.keyboard.press("Tab")

        await page.wait_for_timeout(500)

        campo_fim = page.locator("#datafim")
        await campo_fim.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.type(data_fim_fmt, delay=80)
        await page.keyboard.press("Tab")

        await page.wait_for_timeout(500)

        val_ini = await campo_ini.input_value()
        val_fim = await campo_fim.input_value()

        print(f"Valores: {val_ini} até {val_fim}")

        print("🔍 Filtrando...")
        await page.locator("button:has-text('Filtrar')").first.click()

        await page.wait_for_timeout(6000)

        # =========================
        # PAGINAÇÃO
        # =========================
        todas_notas = []
        pagina = 1

        while True:
            print(f"📄 Lendo página {pagina}...")

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

            print(f"Notas encontradas: {len(notas_raw)}")

            if not notas_raw:
                break

            todas_notas.extend(notas_raw)

            # tenta próxima página
            botao_proximo = page.locator("a[rel='next'], button:has-text('Próxima')")

            if await botao_proximo.count() == 0:
                print("🚫 Sem paginação")
                break

            try:
                await botao_proximo.first.click()
                await page.wait_for_timeout(5000)
                pagina += 1
            except:
                print("🚫 Fim da paginação")
                break

        print(f"✅ Total de notas: {len(todas_notas)}")
        return todas_notas

    except Exception as e:
        await page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


async def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        try:
            async with page.expect_download(timeout=30000) as download_info:
                await page.evaluate(f"window.open('{url}', '_blank')")

            download = await download_info.value
            await download.save_as(caminho)

            print(f"📥 XML salvo: {caminho}")
            return True

        except:
            conteudo = await page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{ credentials: 'include' }});
                return await r.text();
            }}""")

            if "<?xml" in conteudo:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)

                print(f"📥 XML via fetch: {caminho}")
                return True

        return False

    except Exception as e:
        print(f"Erro download: {str(e)}")
        return False
