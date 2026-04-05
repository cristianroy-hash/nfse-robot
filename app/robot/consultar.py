import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("table tbody tr", timeout=30000)
        
        notas = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('table tbody tr'))
                .map((row, i) => ({ index: i, texto: row.innerText }))
                .filter(r => r.texto.length > 10 && !r.texto.includes('Nenhum registro'))
                .map(r => ({ index: r.index, numero: `nota_${r.index}` }));
        }""")
        print(f"Notas detectadas na tabela: {len(notas)}")
        return notas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        print(f"-> Acionando menu de ações da nota {idx}...")

        # 1. Localiza a linha e clica no botão de ações (geralmente o último td ou um botão de engrenagem)
        # Vamos tentar clicar no último elemento da linha que costuma abrir o popover
        linha = page.locator("table tbody tr").nth(idx)
        botao_acoes = linha.locator("td").last
        botao_acoes.click()
        
        # 2. Aguarda o popover aparecer (conforme sua descoberta: .popover-content)
        print("   Aguardando menu flutuante (.popover-content)...")
        page.wait_for_selector(".popover-content", timeout=10000)
        
        # 3. Busca o link de download dentro do popover
        # Usamos uma busca por links que contenham "Download/NFSe"
        href = page.evaluate("""() => {
            const link = document.querySelector('.popover-content a[href*="Download/NFSe"]');
            return link ? link.href : null;
        }""")

        if href:
            print(f"   [SUCESSO] Link de download capturado!")
            # Extraímos o ID do link para dar nome ao arquivo
            id_nota = href.split('/')[-1]
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            with page.expect_download(timeout=60000) as download_info:
                page.goto(href)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML {id_nota} salvo!")
            
            # Fecha o popover clicando fora ou esperando sumir
            page.keyboard.press("Escape")
            return True
        else:
            print("   [ERRO] Link de download não encontrado dentro do popover.")
            return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        # Tenta resetar a página para a próxima nota
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
        return False
