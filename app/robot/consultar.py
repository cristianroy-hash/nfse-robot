import os
import re
from datetime import datetime


def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # ================================
        # FORMATAR DATAS
        # ================================
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        # ================================
        # 🔥 AUTENTICAÇÃO VIA CERTIFICADO
        # ================================
        print("Acessando portal raiz para autenticação...")

        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/",
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_timeout(5000)

        print(f"URL após acesso: {page.url}")

        # Valida se autenticou
        if "Login" in page.url:
            raise Exception("❌ Certificado não autenticou (continua no login)")

        print("✅ Autenticado com sucesso!")

        # ================================
        # IR PARA PÁGINA DE NOTAS
        # ================================
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_timeout(3000)

        # ================================
        # PREENCHER FILTROS
        # ================================
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        campo_ini.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_ini_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        campo_fim.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_fim_fmt, delay=80)
        page.keyboard.press("Tab")
        page.wait_for_timeout(500)

        # Validar preenchimento
        val_ini = page.locator("#datainicio").input_value()
        val_fim = page.locator("#datafim").input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # ================================
        # FILTRAR
        # ================================
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(6000)

        # ================================
        # EXTRAÇÃO COM PAGINAÇÃO
        # ================================
        todas_notas = []
        pagina = 1

        while True:
            print(f"📄 Lendo página {pagina}...")

            notas_raw = page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr[data-chave]');
                return Array.from(rows).map(row => {
                    const chaveEncoded = row.getAttribute('data-chave');
                    const situacao = row.getAttribute('data-situacao') || '';
                    const valor = row.getAttribute('data-valor') || '';

                    const tdData = row.querySelector('.td-data');
                    const data = tdData ? tdData.innerText.trim() : '';

                    const tdTomador = row.querySelector('.td-texto-grande');
                    const tomador = tdTomador ? tdTomador.innerText.trim().substring(0, 60) : '';

                    const htmlRow = row.innerHTML;
                    const matchChave = htmlRow.match(/Download\\/NFSe\\/([0-9]{40,60})/);
                    const chaveNumerica = matchChave ? matchChave[1] : null;

                    return {
                        data_chave: chaveEncoded,
                        chave_acesso: chaveNumerica,
                        situacao: situacao,
                        valor: valor,
                        data: data,
                        tomador: tomador,
                        url_download: chaveNumerica
                            ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                            : null
                    };
                });
            }""")

            print(f"Notas encontradas na página {pagina}: {len(notas_raw)}")

            if len(notas_raw) == 0:
                break

            todas_notas.extend(notas_raw)

            # ================================
            # PAGINAÇÃO
            # ================================
            botao_proximo = page.locator("a[rel='next'], button[aria-label='Próxima']")

            if botao_proximo.count() == 0:
                print("🚫 Não há botão de próxima página")
                break

            if not botao_proximo.is_enabled():
                print("🚫 Botão de próxima desabilitado")
                break

            print("➡️ Indo para próxima página...")
            botao_proximo.click()
            page.wait_for_timeout(5000)

            pagina += 1

        print(f"✅ Total de notas coletadas: {len(todas_notas)}")

        return todas_notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        if not url:
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        try:
            with page.expect_download(timeout=60000) as download_info:
                page.evaluate(f"window.open('{url}', '_blank')")

            download = download_info.value
            download.save_as(caminho)

            print(f"XML salvo: {caminho}")
            return True

        except Exception:
            print("Tentando fallback via fetch...")

            conteudo = page.evaluate(f"""async () => {{
                const r = await fetch('{url}', {{
                    credentials: 'include',
                    headers: {{ 'Accept': 'application/xml, text/xml, */*' }}
                }});
                return await r.text();
            }}""")

            if conteudo and len(conteudo) > 100:
                with open(caminho, 'w', encoding='utf-8') as f:
                    f.write(conteudo)

                print(f"XML salvo via fetch: {caminho}")
                return True

        return False

    except Exception as e:
        print(f"Erro ao baixar XML: {str(e)}")
        return False
