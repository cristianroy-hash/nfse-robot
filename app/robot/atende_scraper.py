# ============================================================
# [NOVO v2] app/robot/atende_scraper.py
#
# Scraper Playwright para portais municipais baseados no
# sistema Atende.Net. Adicionado no robô v2 para suporte aos
# municípios de São José/SC, Palhoça/SC e Biguaçu/SC.
#
# Esses municípios NÃO usam o Portal Nacional (nfse.gov.br)
# nem certificado A1 — o acesso é feito com usuário e senha
# diretamente no portal Atende.Net de cada prefeitura.
#
# Fluxo completo:
#   1. Abre browser Playwright (sem certificado — só usuário/senha)
#   2. Acessa o portal municipal informado (portal_url)
#   3. Realiza login com usuário e senha (login_atende)
#   4. Navega para a seção de NFS-e emitidas (navegar_para_notas_emitidas)
#   5. Aplica filtro de período (filtrar_por_periodo)
#   6. Extrai a lista de notas da tabela de resultados (extrair_notas)
#   7. Fecha o browser e retorna a lista de notas como lista de dicts
#
# Portais suportados (todos no mesmo sistema Atende.Net):
#   - São José/SC  → https://nfse-saojose.atende.net/autoatendimento/servicos/nfse
#   - Palhoça/SC   → https://nfse-palhoca.atende.net/autoatendimento/servicos/nfse
#   - Biguaçu/SC   → https://nfse-bigua.atende.net/autoatendimento/servicos/nfse
#
# CORREÇÃO v2.1 (29/04/2026):
#   O portal Atende.Net renderiza o formulário de login via JavaScript
#   (framework web component). O botão "Entrar" existe no DOM mas fica
#   com display:none ou visibility:hidden até que os campos sejam
#   preenchidos corretamente. A solução é:
#     1. Aguardar carregamento completo do JS (domcontentloaded + 3s)
#     2. Preencher campos via page.fill() com scroll e espera entre campos
#     3. Clicar via force=True no Playwright (ignora visibilidade CSS)
#     4. Fallback: executa element.click() via JavaScript puro no DOM
#     5. Fallback final: pressiona Enter no campo de senha
#     6. Screenshots de debug salvas em /tmp para diagnóstico remoto
#
# Ponto de entrada externo: importar_via_atende()
# Verificador de portal:    is_portal_atende()
# ============================================================

import asyncio
from playwright.async_api import async_playwright, Page


# ============================================================
# MAPEAMENTO DE PORTAIS ATENDE.NET SUPORTADOS
# Chave  = fragmento do hostname para identificar o portal
# Valor  = nome legível do município (usado nos logs)
#
# Novos municípios: basta adicionar uma entrada aqui e o
# is_portal_atende() passa a aceitá-los automaticamente.
# ============================================================
PORTAIS_ATENDE = {
    "nfse-saojose.atende.net": "São José/SC",
    "nfse-palhoca.atende.net": "Palhoça/SC",
    "nfse-bigua.atende.net":   "Biguaçu/SC",
}


# ============================================================
# VERIFICADOR: IS_PORTAL_ATENDE
# Retorna True se a URL pertence a um portal Atende.Net
# suportado. Usado em importar.py para validar portal_url
# antes de chamar importar_via_atende().
# ============================================================
def is_portal_atende(portal_url: str) -> bool:
    if not portal_url:
        return False
    return any(host in portal_url for host in PORTAIS_ATENDE)


# ============================================================
# HELPER: SCREENSHOT DE DEBUG
# Salva screenshot em /tmp/atende_debug_NOME.png e imprime
# os primeiros 3000 chars do HTML para diagnóstico remoto.
# Chamado em pontos críticos do fluxo — facilita ajuste de
# seletores sem precisar acessar o servidor diretamente.
# ============================================================
async def _screenshot_debug(page: Page, nome: str):
    try:
        caminho = f"/tmp/atende_debug_{nome}.png"
        await page.screenshot(path=caminho, full_page=True)
        print(f"📸 [Atende Debug] Screenshot: {caminho}")

        html = await page.content()
        print(f"📄 [Atende Debug] HTML trecho ({nome}):")
        print(html[:3000])
        print(f"--- fim trecho HTML ({nome}) ---")
    except Exception as e:
        print(f"⚠️  [Atende Debug] Erro screenshot {nome}: {e}")


# ============================================================
# CRIAR BROWSER (sem certificado)
# O Atende.Net usa usuário/senha — sem mTLS/certificado A1.
# Mantém os mesmos args de ambiente cloud do browser.py
# para compatibilidade com Railway (headless Linux).
#
# CORREÇÃO v2.1: --window-size e viewport maior para garantir
# que elementos do formulário fiquem dentro do viewport visível.
#
# Retorna: (p, browser, context, page)
# ============================================================
async def criar_browser_atende():
    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1280,900",
            "--start-maximized",
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )

    page = await context.new_page()
    # CORREÇÃO v2.1: timeout 30s — falha mais rápido e loga o problema
    page.set_default_timeout(30000)

    print("🌐 [Atende] Browser criado (modo usuário/senha, sem certificado)")
    return p, browser, context, page


# ============================================================
# FECHAR BROWSER
# Sempre chamado no bloco finally de importar_via_atende().
# ============================================================
async def fechar_browser_atende(p, browser):
    try:
        await browser.close()
        await p.stop()
        print("🔒 [Atende] Browser fechado")
    except Exception as e:
        print(f"⚠️  [Atende] Erro ao fechar browser: {e}")


# ============================================================
# LOGIN NO PORTAL ATENDE.NET
#
# CORREÇÃO v2.1 — problema identificado no log:
#   "element is not visible" no botão btn_entrar.
#   O formulário Atende.Net é renderizado por web component JS.
#   O botão existe no DOM mas fica oculto via CSS até que os
#   campos sejam preenchidos e o componente seja hidratado.
#
# Estratégias de clique implementadas (em ordem de tentativa):
#   1. scroll_into_view + force=True (ignora checks de visibilidade)
#   2. JavaScript element.click() direto no DOM (não depende de CSS)
#   3. Pressionar Enter no campo de senha (equivale a submit)
#
# Retorna True se logado, False se todas as estratégias falharem.
# ============================================================
async def login_atende(page: Page, portal_url: str, usuario: str, senha: str) -> bool:
    print(f"🌐 [Atende] Acessando: {portal_url}")

    # Aguarda carregamento completo do JavaScript do portal
    await page.goto(portal_url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(3000)   # hidratação dos web components

    await _screenshot_debug(page, "01_pagina_inicial")

    # ── Campo de usuário — tenta seletores do mais ao menos específico ──
    seletores_usuario = [
        "input[name='login']",
        "input[id='login']",
        "input[placeholder*='usuário']",
        "input[placeholder*='usuario']",
        "input[placeholder*='CPF']",
        "input[placeholder*='CNPJ']",
        "input[type='text']:visible",
        "input[type='text']",
    ]

    campo_usuario = None
    for sel in seletores_usuario:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo usuário: {sel}")
            campo_usuario = elem
            break

    if not campo_usuario:
        print("❌ [Atende] Campo de usuário não encontrado")
        await _screenshot_debug(page, "02_erro_usuario")
        return False

    await campo_usuario.scroll_into_view_if_needed()
    await page.wait_for_timeout(500)

    # CORREÇÃO v2.2: digita caractere por caractere simulando digitação humana
    # O Atende.Net usa web components que escutam eventos "input" e "change"
    # individuais — um fill() único não dispara esses eventos corretamente
    # e o botão permanece desabilitado/oculto pois o componente não detecta
    # que os campos foram preenchidos.
    await campo_usuario.click()
    await page.keyboard.type(usuario, delay=80)
    await campo_usuario.dispatch_event("input")
    await campo_usuario.dispatch_event("change")
    print(f"✏️  [Atende] Usuário digitado: {usuario}")
    await page.wait_for_timeout(1200)

    # ── Campo de senha ────────────────────────────────────────
    seletores_senha = [
        "input[name='senha']",
        "input[id='senha']",
        "input[type='password']",
    ]

    campo_senha = None
    for sel in seletores_senha:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo senha: {sel}")
            campo_senha = elem
            break

    if not campo_senha:
        print("❌ [Atende] Campo de senha não encontrado")
        await _screenshot_debug(page, "03_erro_senha")
        return False

    await campo_senha.scroll_into_view_if_needed()
    await page.wait_for_timeout(500)

    # CORREÇÃO v2.2: mesma abordagem de digitação humana para a senha
    await campo_senha.click()
    await page.keyboard.type(senha, delay=80)
    await campo_senha.dispatch_event("input")
    await campo_senha.dispatch_event("change")
    print("✏️  [Atende] Senha digitada")
    await page.wait_for_timeout(1500)  # aguarda o JS habilitar o botão

    await _screenshot_debug(page, "04_campos_preenchidos")

    # CORREÇÃO v2.2: remove forçadamente o estilo que oculta o botão antes
    # de tentar clicar. O Atende.Net adiciona "display:none" ou "visibility:hidden"
    # via JS no botão quando os campos não passam na validação do componente.
    # Este evaluate expõe o botão independentemente do estado do componente.
    await page.evaluate("""
        () => {
            const btn = document.querySelector("button[name='btn_entrar']");
            if (btn) {
                btn.style.display   = 'block';
                btn.style.visibility = 'visible';
                btn.style.opacity   = '1';
                btn.removeAttribute('disabled');
            }
        }
    """)
    await page.wait_for_timeout(500)

    # ── Clicar no botão Entrar — 3 estratégias ───────────────
    btn_clicado = False

    # ESTRATÉGIA 1: force=True após expor o botão via JS acima
    seletores_btn = [
        "button[name='btn_entrar']",   # seletor exato do log de erro
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Entrar')",
        "button:has-text('Acessar')",
        "button:has-text('Login')",
    ]

    for sel in seletores_btn:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"🖱️  [Atende] Tentando force=True: {sel}")
            try:
                await elem.scroll_into_view_if_needed()
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] force=True funcionou: {sel}")
                btn_clicado = True
                break
            except Exception as e:
                print(f"⚠️  [Atende] force=True falhou ({sel}): {e}")

    # ESTRATÉGIA 2: JavaScript element.click() direto no DOM
    if not btn_clicado:
        print("🔄 [Atende] Fallback: JavaScript element.click()")
        try:
            clicou = await page.evaluate("""
                () => {
                    let btn = document.querySelector("button[name='btn_entrar']");
                    if (!btn) btn = document.querySelector("button[type='submit']");
                    if (!btn) btn = document.querySelector("input[type='submit']");
                    if (!btn) {
                        const botoes = Array.from(document.querySelectorAll('button'));
                        btn = botoes.find(b =>
                            ['Entrar','Acessar','Login'].includes(b.textContent.trim())
                        );
                    }
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            if clicou:
                print("✅ [Atende] JavaScript click bem-sucedido")
                btn_clicado = True
            else:
                print("⚠️  [Atende] JavaScript não encontrou o botão")
        except Exception as e:
            print(f"⚠️  [Atende] Erro JavaScript: {e}")

    # ESTRATÉGIA 3: Enter no campo de senha
    if not btn_clicado:
        print("🔄 [Atende] Fallback final: Enter no campo senha")
        try:
            await campo_senha.press("Enter")
            print("✅ [Atende] Enter pressionado")
            btn_clicado = True
        except Exception as e:
            print(f"⚠️  [Atende] Erro Enter: {e}")

    if not btn_clicado:
        await _screenshot_debug(page, "05_erro_botao")
        return False

    # Aguarda redirecionamento pós-login
    await page.wait_for_timeout(5000)
    await _screenshot_debug(page, "06_pos_login")

    url_atual = page.url
    print(f"📍 [Atende] URL pós-login: {url_atual}")

    # Ainda na página de login = falhou
    if "login" in url_atual.lower() or url_atual.rstrip("/") == portal_url.rstrip("/"):
        erro_texto = ""
        try:
            elem_erro = page.locator(".erro, .alert, .mensagem-erro, [class*='error']").first
            if await elem_erro.count() > 0:
                erro_texto = await elem_erro.inner_text()
        except Exception:
            pass
        print(f"❌ [Atende] Login falhou. Erro na página: '{erro_texto}'")
        return False

    print(f"✅ [Atende] Login OK. URL: {url_atual}")
    return True


# ============================================================
# NAVEGAR PARA NOTAS EMITIDAS
# Localiza link do menu de NFS-e emitidas após o login.
# Usa force=True no clique pois menus do Atende.Net podem
# ter itens parcialmente fora do viewport.
# ============================================================
async def navegar_para_notas_emitidas(page: Page) -> bool:
    await page.wait_for_timeout(2000)
    await _screenshot_debug(page, "07_menu_pos_login")

    links_candidatos = [
        "a:has-text('NFS-e Emitidas')",
        "a:has-text('Notas Emitidas')",
        "a:has-text('Consultar Notas')",
        "a:has-text('Emitidas')",
        "[href*='emitidas']",
        "[href*='nfse']",
    ]

    for sel in links_candidatos:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"🖱️  [Atende] Navegando: {sel}")
            try:
                await elem.click(force=True)
                await page.wait_for_timeout(3000)
                await _screenshot_debug(page, "08_notas_emitidas")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Erro clique {sel}: {e}")

    print("⚠️  [Atende] Menu notas não encontrado — continuando na página atual")
    return True


# ============================================================
# FILTRAR POR PERÍODO
# Preenche campos de data e clica em pesquisar.
# Aceita DD/MM/YYYY ou YYYY-MM-DD (converte automaticamente).
# ============================================================
async def filtrar_por_periodo(page: Page, data_inicio: str, data_fim: str) -> bool:

    def normalizar(d: str) -> str:
        if "-" in d and len(d) == 10:
            p = d.split("-")
            return f"{p[2]}/{p[1]}/{p[0]}"
        return d

    di = normalizar(data_inicio)
    df = normalizar(data_fim)
    print(f"📅 [Atende] Período: {di} → {df}")

    await _screenshot_debug(page, "09_antes_filtro")

    campo_di = page.locator(
        "input[id*='inicio'], input[name*='inicio'], "
        "input[placeholder*='nício'], input[id*='dataInicio'], input[name*='dataInicio']"
    ).first
    if await campo_di.count() > 0:
        await campo_di.scroll_into_view_if_needed()
        await campo_di.triple_click()
        await campo_di.fill(di)
        print(f"✏️  [Atende] Data início: {di}")

    campo_df = page.locator(
        "input[id*='fim'], input[name*='fim'], "
        "input[placeholder*='té'], input[id*='dataFim'], input[name*='dataFim']"
    ).first
    if await campo_df.count() > 0:
        await campo_df.scroll_into_view_if_needed()
        await campo_df.triple_click()
        await campo_df.fill(df)
        print(f"✏️  [Atende] Data fim: {df}")

    seletores_pesquisar = [
        "button:has-text('Pesquisar')",
        "button:has-text('Consultar')",
        "button:has-text('Buscar')",
        "input[value*='Pesquisar']",
        "button[type='submit']",
    ]

    for sel in seletores_pesquisar:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"🔍 [Atende] Pesquisar: {sel}")
            try:
                await elem.click(force=True, timeout=5000)
                await page.wait_for_timeout(4000)
                await _screenshot_debug(page, "10_resultado")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Erro pesquisar {sel}: {e}")

    print("⚠️  [Atende] Botão pesquisar não encontrado")
    return False


# ============================================================
# EXTRAIR NOTAS DA TABELA DE RESULTADOS
# Extrai cada linha como dict compatível com o Tributtus.
# Erros em linhas individuais não interrompem o loop.
# ============================================================
async def extrair_notas(page: Page) -> list:
    notas = []
    await page.wait_for_timeout(2000)
    await _screenshot_debug(page, "11_tabela")

    linhas = page.locator("table tbody tr, .lista-nfse tr, .resultado tr")
    total = await linhas.count()
    print(f"📋 [Atende] Linhas na tabela: {total}")

    for i in range(total):
        try:
            linha = linhas.nth(i)
            colunas = linha.locator("td")
            num_colunas = await colunas.count()

            if num_colunas < 3:
                continue

            textos = []
            for j in range(num_colunas):
                textos.append((await colunas.nth(j).inner_text()).strip())

            link_xml = None
            lxml = linha.locator("a[href*='xml'], a[href*='XML'], a[title*='XML']")
            if await lxml.count() > 0:
                link_xml = await lxml.first.get_attribute("href")

            link_danfse = None
            lpdf = linha.locator(
                "a[href*='danfse'], a[href*='DANFSe'], a[href*='pdf'], a[title*='PDF']"
            )
            if await lpdf.count() > 0:
                link_danfse = await lpdf.first.get_attribute("href")

            nota = {
                "numero_nota":   textos[0] if len(textos) > 0 else None,
                "data_emissao":  textos[1] if len(textos) > 1 else None,
                "valor_servico": textos[2] if len(textos) > 2 else None,
                "tomador":       textos[3] if len(textos) > 3 else None,
                "chave_acesso":  textos[4] if len(textos) > 4 else textos[0],
                "url_download":  link_xml,
                "url_danfse":    link_danfse,
                "origem":        "atende_net",
            }
            notas.append(nota)

        except Exception as e:
            print(f"⚠️  [Atende] Erro linha {i}: {e}")
            continue

    print(f"✅ [Atende] Total extraído: {len(notas)}")
    return notas


# ============================================================
# FUNÇÃO PRINCIPAL: IMPORTAR VIA ATENDE
# Ponto de entrada da rota /importar-notas-municipal.
# Orquestra login → navegação → filtro → extração.
# Sempre fecha o browser no finally, mesmo com erro.
# ============================================================
async def importar_via_atende(
    portal_url: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
) -> list:

    municipio = next(
        (nome for host, nome in PORTAIS_ATENDE.items() if host in portal_url),
        "Município desconhecido"
    )
    print(f"🏙️  [Atende] Iniciando — {municipio}")
    print(f"   Portal : {portal_url}")
    print(f"   Período: {data_inicio} → {data_fim}")

    p, browser, context, page = await criar_browser_atende()

    try:
        login_ok = await login_atende(page, portal_url, usuario, senha)
        if not login_ok:
            raise Exception(
                f"Falha no login em {portal_url}. "
                f"Verifique usuário/senha. "
                f"Consulte logs /tmp/atende_debug_*.png para diagnóstico."
            )

        await navegar_para_notas_emitidas(page)

        filtro_ok = await filtrar_por_periodo(page, data_inicio, data_fim)
        if not filtro_ok:
            print("⚠️  [Atende] Filtro não aplicado — extraindo o que estiver visível")

        notas = await extrair_notas(page)

        print(f"🏁 [Atende] Concluído — {len(notas)} nota(s)")
        return notas

    finally:
        await fechar_browser_atende(p, browser)
