import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # URL correta descoberta pelo diagnóstico
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        print(f"URL atual: {page.url}")

        # Preenche filtro de data via JavaScript
        preencheu = page.evaluate(f"""() => {{
            const inputs = document.querySelectorAll('input[type="text"]');
            let count = 0;
            inputs.forEach(inp => {{
                const name = (inp.name || inp.id || inp.placeholder || '').toLowerCase();
                if (name.includes('inicio') || name.includes('start') || name.includes('de')) {{
                    inp.value = '{data_inicio}';
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    count++;
                }}
                if (name.includes('fim') || name.includes('end') || name.includes('ate')) {{
                    inp.value = '{data_fim}';
                    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                    count++;
                }}
            }});
            return count;
        }}""")
        print(f"Campos preenchidos: {preencheu}")

        # Captura os IDs das notas direto da tabela via data-id
        notas_raw = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-id]');
            return Array.from(rows).map(row => {
                const dataId = row.getAttribute('data-id');
                const competencia = row.querySelector('td:first-child')?.innerText?.trim() || '';
                
                // Busca link de visualização que contém o ID da nota
                const linkVis = row.querySelector('a[href*="Visualizar"]');
                const urlVis = linkVis ? linkVis.href : '';
                
                // Extrai chave de acesso da URL de visualização
                const match = urlVis.match(/\/Index\/([0-9]{40,60})/);
                const chaveAcesso = match ? match[1] : null;

                return {
                    data_id: dataId,
                    competencia: competencia,
                    chave_acesso: chaveAcesso,
                    url_visualizar: urlVis,
                    url_download: chaveAcesso 
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveAcesso
                        : null
                };
            }).filter(n => n.chave_acesso);
        }""")

        print(f"Notas encontradas no dashboard: {len(notas_raw)}")
        for n in notas_raw:
            print(f"  {n['competencia']} — chave: ...{n['chave_acesso'][-10:] if n['chave_acesso'] else 'N/A'}")

        # Filtra por período se tiver data
        notas_filtradas = notas_raw
        if data_inicio and data_fim:
            try:
                from datetime import datetime
                dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
                dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
                notas_filtradas = []
                for nota in notas_raw:
                    try:
                        dt_nota = datetime.strptime(nota["competencia"], "%d/%m/%Y")
                        if dt_ini <= dt_nota <= dt_fim:
                            notas_filtradas.append(nota)
                    except:
                        notas_filtradas.append(nota)
            except:
                notas_filtradas = notas_raw

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
