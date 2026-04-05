import os
import re
from datetime import datetime

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Converte formato YYYY-MM-DD para DD/MM/YYYY que o portal espera
        dt_ini = datetime.strptime(data_inicio, "%Y-%m-%d")
        dt_fim = datetime.strptime(data_fim, "%Y-%m-%d")
        data_ini_fmt = dt_ini.strftime("%d/%m/%Y")
        data_fim_fmt = dt_fim.strftime("%d/%m/%Y")
        print(f"Datas formatadas: {data_ini_fmt} a {data_fim_fmt}")

        # Navega direto para a página de notas emitidas
        # URL descoberta via diagnóstico dos links do dashboard
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/Notas/Emitidas",
            wait_until="networkidle",
            timeout=60000
        )
        page.wait_for_timeout(3000)

        # Preenche data inicial usando o ID do campo descoberto via diagnóstico
        # ID: datainicio — campo tipo text com classe form-control data
        print("Preenchendo data inicial...")
        campo_ini = page.locator("#datainicio")
        campo_ini.click()
        page.keyboard.press("Control+A")  # Seleciona tudo para sobrescrever valor padrão
        page.keyboard.type(data_ini_fmt, delay=80)  # Digita lentamente simulando humano
        page.keyboard.press("Tab")  # Confirma o campo e move para o próximo
        page.wait_for_timeout(500)

        # Preenche data final usando o ID do campo descoberto via diagnóstico
        # ID: datafim — campo tipo text com classe form-control data
        print("Preenchendo data final...")
        campo_fim = page.locator("#datafim")
        campo_fim.click()
        page.keyboard.press("Control+A")  # Seleciona tudo para sobrescrever valor padrão
        page.keyboard.type(data_fim_fmt, delay=80)  # Digita lentamente simulando humano
        page.keyboard.press("Tab")  # Confirma o campo
        page.wait_for_timeout(500)

        # Verifica se os valores foram preenchidos corretamente
        val_ini = page.locator("#datainicio").input_value()
        val_fim = page.locator("#datafim").input_value()
        print(f"Valores nos campos: {val_ini} a {val_fim}")

        # Clica no botão Filtrar para aplicar o período
        print("Clicando em Filtrar...")
        page.locator("button:has-text('Filtrar')").first.click()
        page.wait_for_timeout(6000)  # Aguarda a tabela recarregar via AJAX

        # Diagnóstico após filtrar — verifica o que apareceu na tela
        texto_pos = page.evaluate("() => document.body.innerText.substring(0, 1500)")
        print(f"Texto após filtrar: {texto_pos}")

        # Captura o HTML completo da tabela para análise dos seletores
        html_tabela = page.evaluate("""() => {
            const t = document.querySelector('table');
            return t ? t.outerHTML.substring(0, 4000) : 'sem tabela';
        }""")
        print(f"HTML tabela após filtrar: {html_tabela}")

        # Captura as notas da tabela extraindo:
        # - data-id: ID interno da nota no portal
        # - competencia: data de emissão exibida na primeira coluna
        # - chave_acesso: número de 44+ dígitos extraído da URL de visualização
        # - url_download: URL direta para download do XML montada com a chave de acesso
        notas_raw = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr[data-id]');
            return Array.from(rows).map(row => {
                const dataId = row.getAttribute('data-id');
                const competencia = row.querySelector('td:first-child')?.innerText?.trim() || '';

                // Busca link de visualização que contém a chave de acesso na URL
                const linkVis = row.querySelector('a[href*="Visualizar"]');
                const urlVis = linkVis ? linkVis.href : '';

                // Extrai chave de acesso da URL ex: /Index/42054072...
                const match = urlVis.match(/\\/Index\\/([0-9]{40,60})/);
                const chaveAcesso = match ? match[1] : null;

                return {
                    data_id: dataId,
                    competencia: competencia,
                    chave_acesso: chaveAcesso,
                    url_download: chaveAcesso
                        ? 'https://www.nfse.gov.br/EmissorNacional/Notas/Download/NFSe/' + chaveAcesso
                        : null
                };
            }).filter(n => n.chave_acesso); // Remove notas sem chave de acesso
        }""")

        print(f"Notas encontradas: {len(notas_raw)}")
        for n in notas_raw:
            print(f"  {n['competencia']} — ...{n['chave_acesso'][-10:]}")

        return notas_raw

    except Exception as e:
        # Salva screenshot do estado da página em caso de erro para debug
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

        # Define o caminho local onde o XML será salvo temporariamente
        # O nome do arquivo usa a chave de acesso completa para evitar duplicatas
        caminho = os.path.join(download_dir, f"{chave}.xml")

        # Usa expect_download para capturar o arquivo que o portal envia
        # ao acessar a URL de download direto
        with page.expect_download(timeout=60000) as download_info:
            page.goto(url)

        # Salva o arquivo no diretório temporário
        download_info.value.save_as(caminho)
        print(f"XML salvo: {caminho}")
        return True

    except Exception as e:
        print(f"Erro ao baixar nota {chave}: {str(e)}")
        return False
