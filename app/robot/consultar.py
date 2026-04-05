import os
import re
from datetime import datetime

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        print(f"URL atual: {page.url}")
        texto = page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"Texto da página: {texto}")

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

        notas_filtradas = []
        for nota in notas_raw:
            try:
                dt_nota = datetime.strptime(nota["competencia"], "%d/%m/%Y")
                dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
                dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
                if dt_ini <= dt_nota <= dt_fim:
                    notas_filtradas.append(nota)
            except:
                notas_filtradas.append(nota)

        print(f"Notas no período: {len(notas_filtradas)}")
        return notas_filtradas

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")


def baixar_xml(page, nota: dict, download_dir: str):
    try:
        url = nota.get("url_download")
        chave = nota.get("chave_acesso", "desconhecido")
        print(f"Baixando nota {chave[-10:]}...")

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
