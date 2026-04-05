import os
import traceback
from calendar import monthrange

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO CAPTURA (Competência {competencia}) ---")
        # Recarrega a página para limpar qualquer erro de sessão anterior
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        # Captura apenas índices de linhas que REALMENTE parecem notas
        notas_indices = page.evaluate("""() => {
            const rows = document.querySelectorAll('table tbody tr');
            return Array.from(rows)
                .map((row, i) => ({ text: row.innerText, index: i }))
                .filter(item => item.text.length > 10 && !item.text.includes('Exception') && !item.text.includes('Nenhum registro'))
                .map(item => item.index);
        }""")

        notas_encontradas = []
        for idx in notas_indices:
            try:
                raw_text = page.locator("table tbody tr").nth(idx).locator("td").first.inner_text()
                # Se o texto for gigante (erro do site), limpa
                numero = raw_text.split('\n')[0].strip()
                if len(numero) > 50 or "exception" in numero.lower():
                    numero = f"nota_idx_{idx}"
            except:
                numero = f"nota_{idx}"
            
            notas_encontradas.append({"numero": numero, "index": idx})

        print(f"Notas detectadas após filtro de erro: {len(notas_encontradas)}")
        return notas_encontradas
    except Exception as e:
        print(f"Erro na consulta: {e}")
        return []

def baixar_xml(page, nota: dict, download_dir: str):
    try:
        idx = nota["index"]
        caminho_local = os.path.join(download_dir, f"{nota['numero']}.xml")
        print(f"-> Tentando baixar nota index {idx}")

        # Script injetado que busca o botão de forma exaustiva
        script_download = f"""
        () => {{
            const rows = document.querySelectorAll('table tbody tr');
            const row = rows[{idx}];
            if (!row) return "LINHA_NAO_ENCONTRADA";

            // Busca na última e na penúltima célula (onde costumam ficar as ações)
            const cells = row.querySelectorAll('td');
            const lastCell = cells[cells.length - 1];
            
            // Procura por QUALQUER botão ou link dentro da célula de ações
            const btn = lastCell.querySelector('button') || 
                        lastCell.querySelector('a') || 
                        lastCell.querySelector('.dropdown-toggle') ||
                        row.querySelector('i.fa-cog')?.parentElement; // Tenta achar pela engrenagem

            if (!btn) return "BTN_NOT_FOUND";
            
            btn.click();
            return "CLICOU";
        }}
        """

        # 1. Abre o menu de ações
        res = page.evaluate(script_download)
        if res != "CLICOU":
            print(f"   [AVISO] {res}. Tentando clique direto via coordenada...")
            # Fallback: clica no final da linha se o JS não achou o elemento
            page.locator("table tbody tr").nth(idx).locator("td").last.click()
        
        page.wait_for_timeout(2000)

        # 2. Clica no XML (Busca por texto 'XML' em qualquer lugar da tela agora)
        try:
            with page.expect_download(timeout=60000) as download_info:
                page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a, button, span, li'));
                    const xmlLink = links.find(el => el.innerText.toUpperCase().includes('XML'));
                    if (xmlLink) {
                        xmlLink.click();
                    } else {
                        // Se não achar pelo texto, tenta pelo título do atributo
                        const backup = document.querySelector('[title*="XML"]');
                        if(backup) backup.click();
                    }
                }""")
            
            download = download_info.value
            download.save_as(caminho_local)
            print(f"   [OK] Sucesso: {nota['numero']}.xml")
            return True
        except Exception as e_dl:
            print(f"   [ERRO] Download não disparado. Menu pode não ter aberto: {e_dl}")
            page.keyboard.press("Escape")
            return False

    except Exception as e:
        print(f"   [ERRO FATAL] {e}")
        return False
