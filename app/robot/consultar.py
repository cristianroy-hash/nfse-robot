import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        
        page.wait_for_selector("table tbody tr", timeout=30000)
        page.wait_for_timeout(2000)

        # Apenas detecta quantas linhas existem
        total_notas = page.evaluate("document.querySelectorAll('table tbody tr').length")
        
        notas_encontradas = []
        for i in range(total_notas):
            # Filtra linhas vazias ou de erro
            texto_linha = page.locator("table tbody tr").nth(i).inner_text()
            if len(texto_linha) > 10 and "Nenhum registro" not in texto_linha:
                notas_encontradas.append({"index": i, "numero": f"nota_{i}"})

        print(f"Notas detectadas: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        print(f"-> Localizando Chave de Acesso para nota {idx}...")

        # 1. Clicar no botão de 'Visualizar/Detalhes' (Geralmente o primeiro ícone ou o número da nota)
        # Vamos tentar clicar no link que estiver na linha
        linha = page.locator("table tbody tr").nth(idx)
        btn_detalhe = linha.locator("a, button").first
        btn_detalhe.click()
        
        # 2. Espera os detalhes carregarem e busca a chave (44 dígitos)
        page.wait_for_timeout(3000)
        html_detalhes = page.content()
        
        match = re.search(r'\d{44}', html_detalhes)
        
        if not match:
            print("   [ERRO] Chave não encontrada nos detalhes. Tentando voltar...")
            page.go_back() # Tenta voltar para a lista
            return False
        
        chave = match.group(0)
        print(f"   Chave encontrada: {chave}")

        # 3. Agora que temos a chave, usamos o 'pulo do gato' da URL direta
        url_direta = f"https://www.nfse.gov.br/EmissorNacional/NFSes/Download/XML?chaveAcesso={chave}"
        caminho_local = os.path.join(download_dir, f"{chave}.xml")

        try:
            with page.expect_download(timeout=60000) as download_info:
                page.goto(url_direta)
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] XML salvo via URL direta!")
            
            # 4. Volta para a página da lista para processar a próxima
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
            page.wait_for_selector("table tbody tr")
            return True
        except Exception as e:
            print(f"   [ERRO] Download falhou: {e}")
            page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        return False
