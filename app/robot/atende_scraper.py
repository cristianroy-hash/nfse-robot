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
# Ponto de entrada externo: importar_via_atende()
# Verificador de portal: is_portal_atende()
# ============================================================

import asyncio
from playwright.async_api import async_playwright, Page


# ============================================================
# MAPEAMENTO DE PORTAIS ATENDE.NET SUPORTADOS
# Chave  = fragmento do hostname usado para identificar o portal
# Valor  = nome legível do município (usado nos logs)
#
# O roteamento não usa código IBGE pois o ImportRequest só
# recebe portal_url (enviada pelo frontend do Tributtus).
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
# Retorna True se a URL informada pertence a um portal
# Atende.Net suportado. Usado em importar.py para validar
# o campo portal_url antes de chamar importar_via_atende().
# Retorna False se portal_url for None, vazio ou não listado.
# ============================================================
def is_portal_atende(portal_url: str) -> bool:
    if not portal_url:
        return False
    return any(host in portal_url for host in PORTAIS_ATENDE)


# ============================================================
# CRIAR BROWSER (sem certificado)
# Diferente do browser.py original que exige certificado A1,
# o Atende.Net usa usuário/senha → browser simples sem mTLS.
# Mantém os mesmos args de segurança/ambiente cloud do browser.py
# para garantir compatibilidade com o Railway (headless Linux).
# Retorna: (p, browser, context, page) — sem cert_path/key_path
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
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1280, "height": 800},
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )

    page = await context.new_page()
    page.set_default_timeout(60000)

    print("🌐 [Atende] Browser criado (modo usuário/senha, sem certificado)")
    return p, browser, context, page


# ============================================================
# FECHAR BROWSER
# Equivalente ao _fechar_browser() do importar.py, mas sem
# limpeza de arquivos PEM (não há certificado neste fluxo).
# Sempre chamado no bloco finally de importar_via_atende().
# ============================================================
async def fechar_browser_atende(p, browser):
    try:
        await browser.close()
        await p.stop()
        print("🔒 [Atende] Browser fechado")
    except Exception as e:
        print(f"⚠️ [Atende] Erro ao fechar browser: {e}")


# ============================================================
# LOGIN NO PORTAL ATENDE.NET
# Navega para a portal_url, localiza os campos de usuário e
# senha com seletores amplos (funciona para todos os portais
# Atende.Net pois compartilham a mesma estrutura de HTML).
# Após clicar em Entrar, verifica se saiu da página de login.
# Retorna True se logado, False se falhou.
# ============================================================
async def login_atende(page: Page, portal_url: str, usuario: str, senha: str) -> bool:
    print(f"🌐 [Atende] Acessando portal: {portal_url}")
    await page.goto(portal_url, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)

    # ── Localiza e preenche o campo de usuário ────────────────
    # Seletores em ordem de especificidade: name → id → type
    campo_usuario = page.locator(
        "input[name='login'], input[id='login'], input[type='text']"
    ).first
    if await campo_usuario.count() == 0:
        print("❌ [Atende] Campo de usuário não encontrado na página")
        return False
    await campo_usuario.fill(usuario)
    print("✏️  [Atende] Usuário preenchido")

    # ── Localiza e preenche o campo de senha ──────────────────
    campo_senha = page.locator(
        "input[name='senha'], input[id='senha'], input[type='password']"
    ).first
    if await campo_senha.count() == 0:
        print("❌ [Atende] Campo de senha não encontrado na página")
        return False
    await campo_senha.fill(senha)
    print("✏️  [Atende] Senha preenchida")

    # ── Localiza e clica no botão de login ────────────────────
    btn_entrar = page.locator(
        "button[type='submit'], input[type='submit'], "
        "button:has-text('Entrar'), button:has-text('Acessar')"
    ).first
    await btn_entrar.click()
    await page.wait_for_timeout(4000)

    # ── Verifica se o login foi bem-sucedido ──────────────────
    # Se ainda estiver numa URL com "login" ou "acesso" → falhou
    url_atual = page.url
    if "login" in url_atual.lower() or "acesso" in url_atual.lower():
        print(f"❌ [Atende] Login falhou — ainda na página de login: {url_atual}")
        return False

    print(f"✅ [Atende] Login realizado com sucesso. URL atual: {url_atual}")
    return True


# ============================================================
# NAVEGAR PARA NOTAS EMITIDAS
# Após o login, localiza o link ou menu de NFS-e emitidas.
# Tenta múltiplos seletores em ordem de probabilidade para
# cobrir variações entre os portais dos diferentes municípios.
# Retorna True sempre (mesmo sem encontrar o link) pois o
# filtro de datas pode estar disponível na mesma página pós-login.
# ============================================================
async def navegar_para_notas_emitidas(page: Page) -> bool:
    # Lista de seletores candidatos em ordem de especificidade
    links_candidatos = [
        "a:has-text('NFS-e Emitidas')",
        "a:has-text('Notas Emitidas')",
        "a:has-text('Consultar Notas')",
        "a:has-text('Emitidas')",
        "[href*='emitidas']",
        "[href*='nfse']",
    ]

    for seletor in links_candidatos:
        elem = page.locator(seletor).first
        if await elem.count() > 0:
            print(f"🖱️  [Atende] Navegando para notas emitidas via seletor: {seletor}")
            await elem.click()
            await page.wait_for_timeout(3000)
            return True

    # Nenhum link encontrado — pode ser que o filtro já esteja na página atual
    print("⚠️  [Atende] Link de notas emitidas não encontrado — continuando na URL atual")
    return True


# ============================================================
# FILTRAR POR PERÍODO
# Preenche os campos de data início e fim e dispara a consulta.
# Aceita datas em DD/MM/YYYY ou YYYY-MM-DD (converte automaticamente).
# Tenta seletores comuns do Atende.Net para os campos de data
# e para o botão de pesquisa/consulta.
# Retorna True se o botão foi encontrado e clicado, False caso contrário.
# ============================================================
async def filtrar_por_periodo(page: Page, data_inicio: str, data_fim: str) -> bool:

    # ── Normaliza para DD/MM/YYYY (formato esperado pelo Atende.Net) ──
    def normalizar(d: str) -> str:
        if "-" in d and len(d) == 10:           # YYYY-MM-DD → DD/MM/YYYY
            partes = d.split("-")
            return f"{partes[2]}/{partes[1]}/{partes[0]}"
        return d                                  # já está em DD/MM/YYYY

    di = normalizar(data_inicio)
    df = normalizar(data_fim)
    print(f"📅 [Atende] Aplicando filtro de período: {di} → {df}")

    # ── Campo de data início ──────────────────────────────────
    campo_di = page.locator(
        "input[id*='inicio'], input[name*='inicio'], "
        "input[placeholder*='nício'], input[id*='de']"
    ).first
    if await campo_di.count() > 0:
        await campo_di.triple_click()   # seleciona tudo antes de preencher
        await campo_di.fill(di)
        print(f"✏️  [Atende] Data início preenchida: {di}")

    # ── Campo de data fim ─────────────────────────────────────
    campo_df = page.locator(
        "input[id*='fim'], input[name*='fim'], "
        "input[placeholder*='té'], input[id*='ate'], input[id*='até']"
    ).first
    if await campo_df.count() > 0:
        await campo_df.triple_click()
        await campo_df.fill(df)
        print(f"✏️  [Atende] Data fim preenchida: {df}")

    # ── Botão de pesquisa / consulta ──────────────────────────
    btn_pesquisar = page.locator(
        "button:has-text('Pesquisar'), button:has-text('Consultar'), "
        "button:has-text('Buscar'), input[value*='Pesquisar']"
    ).first
    if await btn_pesquisar.count() > 0:
        await btn_pesquisar.click()
        await page.wait_for_timeout(4000)
        print("🔍 [Atende] Pesquisa disparada")
        return True

    print("⚠️  [Atende] Botão de pesquisa não encontrado — resultado pode já estar visível")
    return False


# ============================================================
# EXTRAIR NOTAS DA TABELA DE RESULTADOS
# Localiza a tabela de resultados após o filtro e extrai cada
# linha como um dict compatível com o import_service do Tributtus.
# Campos capturados: número, data, valor, tomador, chave, links XML/DANFSe.
# Linhas com menos de 3 colunas são ignoradas (cabeçalho, rodapé, etc).
# Erros em linhas individuais são logados mas não interrompem o loop.
# ============================================================
async def extrair_notas(page: Page) -> list:
    notas = []

    # Aguarda estabilização da tabela após a pesquisa
    await page.wait_for_timeout(2000)

    # Seletores candidatos para a tabela de resultados do Atende.Net
    linhas = page.locator("table tbody tr, .lista-nfse tr, .resultado tr")
    total = await linhas.count()
    print(f"📋 [Atende] Linhas encontradas na tabela: {total}")

    for i in range(total):
        try:
            linha = linhas.nth(i)
            colunas = linha.locator("td")
            num_colunas = await colunas.count()

            # Ignora linhas de cabeçalho, separadores ou linhas vazias
            if num_colunas < 3:
                continue

            # ── Extrai texto de cada coluna ───────────────────
            textos = []
            for j in range(num_colunas):
                textos.append((await colunas.nth(j).inner_text()).strip())

            # ── Tenta capturar link de download do XML ────────
            link_xml = None
            links_xml = linha.locator(
                "a[href*='xml'], a[href*='XML'], a[title*='XML']"
            )
            if await links_xml.count() > 0:
                link_xml = await links_xml.first.get_attribute("href")

            # ── Tenta capturar link do DANFSe (PDF) ──────────
            link_danfse = None
            links_pdf = linha.locator(
                "a[href*='danfse'], a[href*='DANFSe'], "
                "a[href*='pdf'], a[title*='PDF']"
            )
            if await links_pdf.count() > 0:
                link_danfse = await links_pdf.first.get_attribute("href")

            # ── Monta o dict no formato esperado pelo Tributtus ──
            # A ordem das colunas segue o padrão mais comum do Atende.Net:
            #   [0] número da nota
            #   [1] data de emissão
            #   [2] valor do serviço
            #   [3] nome do tomador
            #   [4] chave de acesso (se existir coluna extra)
            nota = {
                "numero_nota":   textos[0] if len(textos) > 0 else None,
                "data_emissao":  textos[1] if len(textos) > 1 else None,
                "valor_servico": textos[2] if len(textos) > 2 else None,
                "tomador":       textos[3] if len(textos) > 3 else None,
                "chave_acesso":  textos[4] if len(textos) > 4 else textos[0],
                "url_download":  link_xml,
                "url_danfse":    link_danfse,
                "origem":        "atende_net",   # identifica a origem para o Tributtus
            }
            notas.append(nota)

        except Exception as e:
            # Erro em linha individual não interrompe o loop
            print(f"⚠️  [Atende] Erro ao extrair linha {i}: {e}")
            continue

    print(f"✅ [Atende] Total de notas extraídas: {len(notas)}")
    return notas


# ============================================================
# FUNÇÃO PRINCIPAL: IMPORTAR VIA ATENDE
# Ponto de entrada chamado pela rota /importar-notas-municipal
# em importar.py. Orquestra todo o fluxo do scraping Atende.Net:
#   1. Cria o browser (sem certificado)
#   2. Faz login com usuário/senha
#   3. Navega para notas emitidas
#   4. Aplica filtro de período
#   5. Extrai notas da tabela
#   6. Fecha o browser (sempre, mesmo com erro)
#   7. Retorna lista de notas ou lança Exception
#
# Parâmetros:
#   portal_url   → URL completa do portal Atende.Net do município
#   usuario      → usuário cadastrado no portal municipal
#   senha        → senha cadastrada no portal municipal
#   data_inicio  → data inicial do período (DD/MM/YYYY ou YYYY-MM-DD)
#   data_fim     → data final do período (DD/MM/YYYY ou YYYY-MM-DD)
#
# Retorno:
#   list[dict] com as notas encontradas no período
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
    print(f"🏙️  [Atende] Iniciando importação — {municipio}")
    print(f"   Portal  : {portal_url}")
    print(f"   Período : {data_inicio} → {data_fim}")

    p, browser, context, page = await criar_browser_atende()

    try:
        # ── Passo 1: Login ────────────────────────────────────
        login_ok = await login_atende(page, portal_url, usuario, senha)
        if not login_ok:
            raise Exception(
                f"Falha no login no portal {portal_url}. "
                f"Verifique usuário e senha do cliente."
            )

        # ── Passo 2: Navegar para notas emitidas ──────────────
        await navegar_para_notas_emitidas(page)

        # ── Passo 3: Aplicar filtro de período ────────────────
        filtro_ok = await filtrar_por_periodo(page, data_inicio, data_fim)
        if not filtro_ok:
            # Não lança exception — pode haver notas visíveis mesmo sem filtrar
            print("⚠️  [Atende] Filtro de datas não aplicado — tentando extrair mesmo assim")

        # ── Passo 4: Extrair notas da tabela ──────────────────
        notas = await extrair_notas(page)

        print(f"🏁 [Atende] Importação finalizada — {len(notas)} nota(s) encontrada(s)")
        return notas

    finally:
        # Fecha o browser SEMPRE, mesmo em caso de exceção
        await fechar_browser_atende(p, browser)
