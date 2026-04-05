def consultar_notas(page, competencia: str):
    try:
        ano, mes = competencia.split("-")
        
        print(f"Navegando para consulta de notas...")
        # Aumentei o timeout e mudei para 'networkidle' para garantir que os scripts carregaram
        page.goto(
            "https://www.nfse.gov.br/EmissorNacional/NFSes/Emitidas",
            wait_until="networkidle",
            timeout=90000
        )
        page.wait_for_timeout(5000) # Pausa extra para renderização
        
        print(f"URL alcançada: {page.url}")
        print(f"Título da página: {page.title()}")
        
        # Tira um print do que o robô está vendo AGORA
        page.screenshot(path="/tmp/debug_consulta.png")
        print("Screenshot de debug salvo em /tmp/debug_consulta.png")

        # Verifica se há Iframes (comum em portais do governo)
        frames = page.frames
        print(f"Total de frames encontrados: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: Name={frame.name}, URL={frame.url}")

        # Seu código de scan de elementos (melhorado com logs)
        elementos = page.evaluate("""() => {
            const tags = document.querySelectorAll('input, select, button, a, label, span');
            return Array.from(tags).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                class: el.className || '',
                text: (el.innerText || el.value || '').substring(0, 50).trim()
            }));
        }""")
        
        print("--- MAPEAMENTO DE ELEMENTOS ---")
        for el in elementos:
            # Filtra apenas elementos que pareçam úteis para não inundar o log
            if el['id'] or el['name'] or el['text'] or 'data' in el['class'].lower():
                print(f"  {el}")
        
        # Imprime o HTML para análise profunda
        html = page.content()
        print(f"--- HTML PREVIEW (Primeiros 2000 chars) ---")
        print(html[:2000])

        # Retornamos vazio apenas para esta rodada de testes
        return []

    except Exception as e:
        print(f"Erro durante o scan: {str(e)}")
        raise Exception(f"Falha na consulta: {str(e)}")
