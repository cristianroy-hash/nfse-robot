import os
import re

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        # Aumentamos o timeout para garantir carga completa
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=90000)
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

        # 1. Mira no botão de ações dentro da última célula
        # Muitas vezes é um elemento com classe 'btn' ou um ícone 'fa-cog' / 'fa-list'
        celula_acoes = page.locator("table tbody tr").nth(idx).locator("td").last
        
        # Tenta clicar no botão específico dentro da célula, se não houver, clica na célula
        botao = celula_acoes.locator("button, a, i").first
        if botao.count() > 0:
            botao.click(force=True)
        else:
            celula_acoes.click(force=True)
        
        # 2. Aguarda o popover aparecer (com tolerância maior e sem checar visibilidade estrita)
        print("   Aguardando menu flutuante (.popover-content)...")
        try:
            page.wait_for_selector(".popover-content", state="attached", timeout=15000)
        except:
            print("   [AVISO] Popover não detectado via seletor padrão. Tentando clique alternativo...")
            # Plano B: Clica em qualquer lugar da linha para ver se o menu brota
            page.locator("table tbody tr").nth(idx).click()
            page.wait_for_timeout(2000)

        # 3. Extração do link via JavaScript direto no DOM (mais rápido que o seletor do Playwright)
        href = page.evaluate("""() => {
            // Procura em qualquer lugar da página por um link de download de NFSe
            const link = document.querySelector('a[href*="Download/NFSe"], .popover-content a[href*="Download"]');
            return link ? link.href : null;
        }""")

        if href:
            print(f"   [SUCESSO] Link capturado: {href[:60]}...")
            id_nota = href.split('/')[-1]
            caminho_local = os.path.join(download_dir, f"{id_nota}.xml")

            with page.expect_download(timeout=60000) as download_info:
                page.goto(href)
            
            download_info.value.save_as(caminho_local)
            print(f"   [OK] XML salvo!")
            return True
        else:
            print("   [ERRO] Link de download não encontrado na página após clique.")
            return False

    except Exception as e:
        print(f"   [FALHA] {e}")
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas")
        return False
