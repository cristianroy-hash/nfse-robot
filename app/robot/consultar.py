import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # O dashboard já mostra as notas — vamos capturar direto dali
        print("Capturando notas do dashboard...")
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Captura HTML completo do dashboard para analisar estrutura da tabela
        dados = page.evaluate("""() => {
            const tabela = document.querySelector('table');
            return {
                html_tabela: tabela ? tabela.outerHTML.substring(0, 5000) : 'sem tabela',
                links_download: Array.from(document.querySelectorAll('a[href*="Download"], a[href*="NFSe"], a[href*="download"]'))
                    .map(a => ({ text: a.innerText.trim(), href: a.href })),
                todas_hrefs: Array.from(document.querySelectorAll('a'))
                    .map(a => ({ text: a.innerText.trim().substring(0, 40), href: a.href }))
                    .filter(a => a.href && a.href !== window.location.href)
            }
        }""")

        print(f"HTML tabela: {dados['html_tabela']}")
        print(f"Links download: {dados['links_download']}")
        print(f"Todas hrefs: {dados['todas_hrefs']}")

        return []

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    return False
