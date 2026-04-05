import os

def consultar_notas(page, competencia: str):
    try:
        print(f"--- INICIANDO SCAN DE DIAGNÓSTICO ---")
        # Forçamos a ida para a página de notas
        page.goto("https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        
        print(f"URL Alcançada: {page.url}")
        
        # Scanner para mapearmos a página real
        dados = page.evaluate("""() => {
            return {
                texto: document.body.innerText.substring(0, 1000),
                inputs: Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id, name: i.name, class: i.className, placeholder: i.placeholder
                })),
                buttons: Array.from(document.querySelectorAll('button')).map(b => ({
                    text: b.innerText, id: b.id
                }))
            };
        }""")
        
        print(f"TEXTO NA TELA: {dados['texto']}")
        print(f"INPUTS ENCONTRADOS: {dados['inputs']}")
        print(f"BOTÕES ENCONTRADOS: {dados['buttons']}")
        
        return [] # Retorna lista vazia para não dar erro no loop de notas

    except Exception as e:
        print(f"Erro no scan: {str(e)}")
        raise Exception(f"Falha na consulta: {str(e)}")

# Mantenha esta função aqui embaixo para o import_service não quebrar
def baixar_xml(page, nota: dict, download_dir: str):
    return True
