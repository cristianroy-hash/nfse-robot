import os
import re
from datetime import datetime

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Converte formato YYYY-MM-DD para DD/MM/YYYY
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)
        print(f"URL atual: {page.url}")

        # Captura os inputs de data disponíveis
        inputs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(i => ({
                id: i.id, name: i.name, type: i.type,
                class: i.className, placeholder: i.placeholder,
                value: i.value
            }));
        }""")
        print(f"Inputs disponíveis: {inputs}")

        # Preenche data inicial
        try:
            campo_ini = page.locator("input").nth(0)
            campo_ini.click()
            campo_ini.fill("")
            page.keyboard.type(data_ini_fmt, delay=80)
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            print(f"Data inicial preenchida: {data_ini_fmt}")
        except Exception as e:
            print(f"Erro ao preencher data inicial: {e}")

        # Preenche data final
        try:
            campo_fim = page.locator("input").nth(1)
            campo_fim.click()
            campo_fim.fill("")
            page.keyboard.type(data_fim_fmt, delay=80)
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            print(f"Data final preenchida: {data_fim_fmt}")
        except Exception as e:
            print(f"Erro ao preencher data final: {e}")

        # Clica em Filtrar
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(5000)

        # Captura notas da tabela
        notas_raw = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-id]');
            return Array.from(rows).map(row => {
                const dataId = row.getAttribute('data-id');
                const competencia = row.querySelector('td:first-child')?.innerText?.trim() || '';
                const linkVis = row.querySelector('a[href*="Visualizar"]');
                const urlVis = linkVis ? linkVis.href : '';
                const match = urlVis.match(/\/Index\/([0-9]{40,60})/);
                const chaveAcesso = match ? match[1] : null;
                return {
                    data_id: dataId,
                    competencia: competencia,
                    chave_acesso: chaveAcesso,
                    url_download: chaveAcesso
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveAcesso
                        : null
                };
            }).filter(n => n.chave_acesso);
        }""")

        print(f"Notas encontradas: {len(notas_raw)}")
        for n in notas_raw:
            print(f"  {n['competencia']} — {n['chave_acesso'][-10:] if n['chave_acesso'] else 'N/A'}")

        return notas_raw

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso", "desconhecido")
        print(f"Baixando nota ...{chave[-10:]}...")

        if not url:
            print("Sem URL de download")
            return False

        caminho = os.path.join(download_dir, f"{chave}.xml")

        with page.expect_download(timeout=60000) as download_info:
            page.goto(url)

        download_info.value.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
