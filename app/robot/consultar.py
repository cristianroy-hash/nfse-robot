import os
import re
from datetime import datetime


def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")

        # =========================
        # ACESSA PÁGINA
        # =========================
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # =========================
        # PREENCHE DATAS
        # =========================
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        campo_ini.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_ini_fmt, delay=80)

        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        campo_fim.click()
        page.keyboard.press("Control+A")
        page.keyboard.type(data_fim_fmt, delay=80)

        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(6000)

        # =========================
        # PAGINAÇÃO
        # =========================
        todas_notas = []
        pagina = 1

        while True:
            print(f"📄 Lendo página {pagina}")

            notas_raw = page.evaluate("""() => {
                const rows = document.querySelectorAll('table tbody tr[data-chave]');
                return Array.from(rows).map(row => {
                    const htmlRow = row.innerHTML;
                    const matchChave = htmlRow.match(/Download\\/NFSe\\/([0-9]{40,60})/);
                    const chaveNumerica = matchChave ? matchChave[1] : null;

                    return {
                        chave_acesso: chaveNumerica,
                        url_download: chaveNumerica
                            ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveNumerica
                            : null
                    };
                });
            }""")

            print(f"➡️ {len(notas_raw)} notas nesta página")

            if len(notas_raw) == 0:
                print("🚫 Nenhuma nota encontrada")
                break

            todas_notas.extend(notas_raw)

            # =========================
            # BOTÃO PRÓXIMO
            # =========================
            botao_proximo = page.locator(
                "li.page-item:not(.disabled) a[aria-label='Próximo'], li.page-item:not(.disabled) a:has-text('›')"
            )

            if botao_proximo.count() == 0:
                print("🚫 Última página atingida")
                break

            try:
                print("➡️ Indo para próxima página...")
                botao_proximo.first.click()
                page.wait_for_timeout(5000)
                pagina += 1
            except Exception as e:
                print(f"Erro ao navegar página: {str(e)}")
                break

        print(f"✅ Total de notas coletadas: {len(todas_notas)}")

        return todas_notas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


# =========================
# DOWNLOAD XML (MANTIDO)
# =========================
def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso") or nota.get("data_chave", "desconhecido")
        nome_arquivo = nota.get("chave_acesso") or nota.get("data_chave", "nota")

        print(f"Baixando nota ...{str(chave)[-10:]}...")

        if not url:
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{nome_arquivo}.xml")

        with page.expect_download(timeout=60000) as download_info:
            page.evaluate(f"window.open('{url}', '_blank')")

        download = download_info.value
        download.save_as(caminho)

        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {str(chave)[-10:]}: {str(e)}")

        # fallback via fetch
        try:
            print("Tentando download via fetch...")
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

        except Exception as e2:
            print(f"Fallback fetch falhou: {str(e2)}")

        return False

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
