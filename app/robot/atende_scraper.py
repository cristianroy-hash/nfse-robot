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
# Fluxo real mapeado (29/04/2026):
#   1. Acessa o portal municipal (portal_url)
#   2. Preenche usuário (CPF/CNPJ) e senha
#   3. Clica em Entrar
#   4. Tela intermediária com botão "Acessar" → clica
#   5. Tela de captcha "Não sou robô" → clica no checkbox
#      (playwright-stealth v2 tenta passar sem exibir o desafio)
#   6. Redireciona para https://nfse-*.atende.net/?rot=1&aca=1#!/sistema/66
#   7. Fecha popup de aviso (se existir)
#   8. Clica no card "Gerenciamento de Notas"
#   9. No filtro, seleciona "Competência" e digita MM/YYYY
#  10. Clica em "Consultar"
#  11. Clica em "Download Todos" → seleciona "XML IPM"
#  12. Aguarda o download e retorna os arquivos/metadados
#
# Dependências adicionadas ao requirements.txt:
#   playwright-stealth>=2.0.0
#
# Portais suportados (todos no mesmo sistema Atende.Net):
#   - São José/SC  → https://nfse-saojose.atende.net/...
#   - Palhoça/SC   → https://nfse-palhoca.atende.net/...
#   - Biguaçu/SC   → https://nfse-bigua.atende.net/...
#
# Ponto de entrada externo: importar_via_atende()
# Verificador de portal:    is_portal_atende()
# ============================================================

import os
import asyncio
import tempfile
from datetime import datetime
from playwright.async_api import async_playwright, Page

# ============================================================
# [NOVO v2] PLAYWRIGHT-STEALTH v2.x
# Importado com fallback seguro: se não estiver instalado no
# deploy atual, o robô continua funcionando sem stealth (mas
# pode ser bloqueado pelo captcha). Adicione playwright-stealth
# ao requirements.txt para ativar.
#
# API correta para v2.x: Stealth().use_async(page)
# APIs antigas (v1.x) stealth_async(page) e stealth_sync(page)
# foram descontinuadas — NÃO usar.
# ============================================================
try:
    from playwright_stealth import Stealth
    STEALTH_DISPONIVEL = True
    print("✅ [Atende] playwright-stealth v2 disponível")
except ImportError:
    STEALTH_DISPONIVEL = False
    print("⚠️  [Atende] playwright-stealth não instalado — captcha pode bloquear")


# ============================================================
# MAPEAMENTO DE PORTAIS ATENDE.NET SUPORTADOS
# Chave  = fragmento do hostname para identificação
# Valor  = nome legível do município (usado nos logs)
#
# Para adicionar novos municípios: basta incluir uma entrada.
# O is_portal_atende() e o log passam a reconhecê-lo automaticamente.
# ============================================================
PORTAIS_ATENDE = {
    "nfse-saojose.atende.net": "São José/SC",
    "nfse-palhoca.atende.net": "Palhoça/SC",
    "nfse-bigua.atende.net":   "Biguaçu/SC",
}


# ============================================================
# VERIFICADOR: IS_PORTAL_ATENDE
# Retorna True se a URL pertence a um portal Atende.Net
# suportado. Chamado em importar.py para validar portal_url
# antes de chamar importar_via_atende().
# ============================================================
def is_portal_atende(portal_url: str) -> bool:
    if not portal_url:
        return False
    return any(host in portal_url for host in PORTAIS_ATENDE)


# ============================================================
# HELPER: SCREENSHOT DE DEBUG
# Salva screenshot em /tmp para diagnóstico remoto.
# Os logs do Railway mostram o caminho — útil para identificar
# em qual etapa o scraper travou.
# ============================================================
async def _screenshot_debug(page: Page, nome: str):
    try:
        caminho = f"/tmp/atende_debug_{nome}_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=caminho, full_page=True)
        print(f"📸 [Atende] Screenshot salva: {caminho}")
    except Exception as e:
        print(f"⚠️  [Atende] Erro ao salvar screenshot {nome}: {e}")


# ============================================================
# CRIAR BROWSER COM STEALTH
# Usa playwright-stealth v2 para mascarar o Playwright como
# um navegador humano — isso é o que permite passar pelo
# captcha "Não sou robô" apenas com o clique no checkbox,
# sem precisar de serviço externo de resolução de captcha.
#
# Diferenças do browser.py original:
#   - Sem certificado A1 (login por usuário/senha)
#   - Com stealth aplicado via Stealth().use_async(page)
#   - download_path configurado para capturar arquivos ZIP/XML
# ============================================================
async def criar_browser_atende(download_dir: str):
    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            # STEALTH: remove a flag que identifica o Chromium como automatizado
            "--disable-blink-features=AutomationControlled",
            # STEALTH: simula GPU para não parecer headless
            "--disable-gpu",
            "--disable-software-rasterizer",
        ]
    )

    context = await browser.new_context(
        viewport={"width": 1366, "height": 768},   # resolução comum de notebook
        ignore_https_errors=True,
        # STEALTH: user-agent de Chrome real (sem "HeadlessChrome" no UA)
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        # STEALTH: locale e timezone brasileiros para parecer usuário local
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        # Configura diretório de download para capturar XMLs
        accept_downloads=True,
    )

    page = await context.new_page()
    page.set_default_timeout(60000)

    # ── Aplica stealth ANTES de navegar para qualquer página ──
    # IMPORTANTE: stealth deve ser aplicado na page, não no context,
    # e antes do primeiro goto() para que os patches JS sejam
    # injetados no document antes de qualquer script do site rodar.
    if STEALTH_DISPONIVEL:
        await Stealth().use_async(page)
        print("🥷 [Atende] Stealth v2 aplicado na page")

    print("🌐 [Atende] Browser criado com sucesso")
    return p, browser, context, page


# ============================================================
# FECHAR BROWSER
# Sempre chamado no bloco finally de importar_via_atende().
# Sem limpeza de PEM pois não há certificado neste fluxo.
# ============================================================
async def fechar_browser_atende(p, browser):
    try:
        await browser.close()
        await p.stop()
        print("🔒 [Atende] Browser fechado")
    except Exception as e:
        print(f"⚠️  [Atende] Erro ao fechar browser: {e}")


# ============================================================
# PASSO 1-3: LOGIN COM USUÁRIO E SENHA
# Navega para o portal, preenche os campos e clica em Entrar.
#
# CORREÇÃO v2.2: digita caractere por caractere com delay=80ms
# para disparar eventos "input"/"change" individuais que o
# web component do Atende.Net precisa para habilitar o botão.
#
# CORREÇÃO v2.2: expõe o botão via JS antes de clicar, pois
# o Atende.Net mantém o botão oculto até validação do componente.
#
# Retorna True se saiu da página de login, False se falhou.
# ============================================================
async def _fazer_login(page: Page, portal_url: str, usuario: str, senha: str) -> bool:
    print(f"🌐 [Atende] Acessando: {portal_url}")
    await page.goto(portal_url, wait_until="networkidle", timeout=90000)
    await page.wait_for_timeout(3000)

    await _screenshot_debug(page, "01_pagina_inicial")

    # ── Campo usuário: tenta seletores em ordem de especificidade ──
    seletores_usuario = [
        "input[name='login']",
        "input[id='login']",
        "input[name='usuario']",
        "input[id='usuario']",
        "input[type='text']:visible",
    ]

    campo_usuario = None
    for sel in seletores_usuario:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo usuário encontrado: {sel}")
            campo_usuario = elem
            break

    if not campo_usuario:
        print("❌ [Atende] Campo de usuário não encontrado")
        await _screenshot_debug(page, "02_erro_usuario")
        return False

    await campo_usuario.scroll_into_view_if_needed()
    await page.wait_for_timeout(500)

    # CORREÇÃO v2.2: keyboard.type dispara eventos por tecla
    # que o web component do Atende.Net precisa para revalidar o form
    await campo_usuario.click()
    await page.keyboard.type(usuario, delay=80)
    await campo_usuario.dispatch_event("input")
    await campo_usuario.dispatch_event("change")
    print(f"✏️  [Atende] Usuário digitado")
    await page.wait_for_timeout(1200)

    # ── Campo senha ───────────────────────────────────────────
    seletores_senha = [
        "input[name='senha']",
        "input[id='senha']",
        "input[type='password']",
    ]

    campo_senha = None
    for sel in seletores_senha:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo senha encontrado: {sel}")
            campo_senha = elem
            break

    if not campo_senha:
        print("❌ [Atende] Campo de senha não encontrado")
        await _screenshot_debug(page, "03_erro_senha")
        return False

    await campo_senha.scroll_into_view_if_needed()
    await campo_senha.click()
    await page.keyboard.type(senha, delay=80)
    await campo_senha.dispatch_event("input")
    await campo_senha.dispatch_event("change")
    print("✏️  [Atende] Senha digitada")
    await page.wait_for_timeout(1500)

    await _screenshot_debug(page, "04_campos_preenchidos")

    # CORREÇÃO v2.2: expõe o botão removendo o CSS que o oculta
    # antes de tentar clicar — o Atende.Net usa display:none até
    # a validação do componente concluir
    await page.evaluate("""
        () => {
            const btn = document.querySelector("button[name='btn_entrar']");
            if (btn) {
                btn.style.display    = 'block';
                btn.style.visibility = 'visible';
                btn.style.opacity    = '1';
                btn.removeAttribute('disabled');
            }
        }
    """)
    await page.wait_for_timeout(500)

    # ── Clicar em Entrar — 3 estratégias em cascata ───────────
    btn_clicado = False

    # ESTRATÉGIA 1: force=True (ignora visibilidade CSS residual)
    seletores_btn = [
        "button[name='btn_entrar']",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Entrar')",
        "button:has-text('Acessar')",
    ]
    for sel in seletores_btn:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Botão Entrar clicado (force): {sel}")
                btn_clicado = True
                break
            except Exception as e:
                print(f"⚠️  [Atende] force=True falhou ({sel}): {e}")

    # ESTRATÉGIA 2: JS element.click() direto no DOM
    if not btn_clicado:
        try:
            clicou = await page.evaluate("""
                () => {
                    let btn = document.querySelector("button[name='btn_entrar']")
                           || document.querySelector("button[type='submit']")
                           || document.querySelector("input[type='submit']");
                    if (!btn) {
                        btn = Array.from(document.querySelectorAll('button'))
                                   .find(b => ['Entrar','Acessar'].includes(b.textContent.trim()));
                    }
                    if (btn) { btn.click(); return true; }
                    return false;
                }
            """)
            if clicou:
                print("✅ [Atende] Botão clicado via JS")
                btn_clicado = True
        except Exception as e:
            print(f"⚠️  [Atende] JS click falhou: {e}")

    # ESTRATÉGIA 3: Enter no campo senha
    if not btn_clicado:
        try:
            await campo_senha.press("Enter")
            print("✅ [Atende] Enter no campo senha")
            btn_clicado = True
        except Exception as e:
            print(f"⚠️  [Atende] Enter falhou: {e}")

    if not btn_clicado:
        print("❌ [Atende] Nenhuma estratégia de clique funcionou")
        await _screenshot_debug(page, "05_erro_botao")
        return False

    # Aguarda redirecionamento pós-clique
    await page.wait_for_timeout(4000)
    await _screenshot_debug(page, "06_pos_entrar")

    # Verifica se ainda está na página de login
    url_atual = page.url
    if "login" in url_atual.lower():
        print(f"❌ [Atende] Ainda na página de login após clique: {url_atual}")
        return False

    print(f"✅ [Atende] Login realizado. URL: {url_atual}")
    return True


# ============================================================
# PASSO 4: BOTÃO "ACESSAR" NA TELA INTERMEDIÁRIA
# Após o login, o Atende.Net exibe uma tela intermediária com
# um botão "Acessar" antes do captcha. Clica nesse botão.
# ============================================================
async def _clicar_acessar(page: Page) -> bool:
    print("🖱️  [Atende] Procurando botão 'Acessar' intermediário...")
    await page.wait_for_timeout(2000)

    seletores = [
        "button:has-text('Acessar')",
        "a:has-text('Acessar')",
        "input[value='Acessar']",
        "button:has-text('Continuar')",
        "button:has-text('Prosseguir')",
    ]

    for sel in seletores:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Botão Acessar clicado: {sel}")
                await page.wait_for_timeout(3000)
                await _screenshot_debug(page, "07_pos_acessar")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Erro ao clicar Acessar ({sel}): {e}")

    # Pode não existir em todos os portais — não é crítico
    print("ℹ️   [Atende] Botão Acessar não encontrado — pode não existir neste portal")
    return True


# ============================================================
# PASSO 5: CAPTCHA "NÃO SOU ROBÔ"
# Com playwright-stealth ativo, o captcha comportamental
# geralmente passa automaticamente sem exibir o checkbox.
# Caso o checkbox apareça, tenta clicar nele diretamente
# dentro do iframe do reCAPTCHA.
#
# Se o stealth não estiver instalado ou o captcha apresentar
# desafio de imagens → retorna False (log indica o problema).
# ============================================================
async def _resolver_captcha(page: Page) -> bool:
    print("🤖 [Atende] Verificando captcha...")
    await page.wait_for_timeout(3000)
    await _screenshot_debug(page, "08_captcha_check")

    # Verifica se há iframe de reCAPTCHA na página
    iframe_recaptcha = page.frame_locator("iframe[src*='recaptcha']").first
    if not iframe_recaptcha:
        # Sem captcha visível — stealth funcionou ou não há captcha
        print("✅ [Atende] Nenhum captcha detectado — stealth funcionou!")
        return True

    # Tenta clicar no checkbox do reCAPTCHA dentro do iframe
    try:
        checkbox = iframe_recaptcha.locator("#recaptcha-anchor").first
        if await checkbox.count() > 0:
            print("🖱️  [Atende] Clicando no checkbox do captcha...")
            await checkbox.click(timeout=10000)
            await page.wait_for_timeout(4000)
            await _screenshot_debug(page, "09_pos_captcha")

            # Verifica se o captcha foi resolvido (checkbox marcado)
            # ou se apareceu desafio de imagens
            desafio_imagens = page.frame_locator("iframe[src*='bframe']").first
            if await page.locator("iframe[src*='bframe']").count() > 0:
                print("❌ [Atende] Captcha apresentou desafio de imagens — não é possível resolver automaticamente")
                print("💡 [Atende] Solução: adicionar serviço 2captcha (veja documentação)")
                return False

            print("✅ [Atende] Captcha resolvido com clique simples")
            return True
    except Exception as e:
        print(f"⚠️  [Atende] Erro ao interagir com captcha: {e}")

    # Sem captcha visível após tentativa — assume que passou
    print("✅ [Atende] Captcha não bloqueou — continuando")
    return True


# ============================================================
# PASSO 6-7: AGUARDAR REDIRECIONAMENTO E FECHAR POPUP
# Após o captcha, aguarda o redirect para #!/sistema/66 e
# fecha qualquer popup de aviso que apareça.
# ============================================================
async def _aguardar_sistema_e_fechar_popup(page: Page):
    print("⏳ [Atende] Aguardando redirecionamento para o sistema...")

    # Aguarda a URL mudar para o sistema (máx 30s)
    try:
        await page.wait_for_url("**/sistema/**", timeout=30000)
        print(f"✅ [Atende] Redirecionado para: {page.url}")
    except Exception:
        print(f"⚠️  [Atende] Timeout aguardando /sistema/ — URL atual: {page.url}")

    await page.wait_for_timeout(3000)
    await _screenshot_debug(page, "10_sistema")

    # Fecha popup de aviso (botão X, Fechar, OK, Entendido)
    seletores_fechar = [
        "button:has-text('Fechar')",
        "button:has-text('OK')",
        "button:has-text('Entendido')",
        "button:has-text('×')",
        "[class*='fechar']",
        "[class*='close']",
        "[aria-label='Close']",
        "[aria-label='Fechar']",
    ]

    for sel in seletores_fechar:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=3000)
                print(f"✅ [Atende] Popup fechado: {sel}")
                await page.wait_for_timeout(1000)
                break
            except Exception:
                pass

    await _screenshot_debug(page, "11_pos_popup")


# ============================================================
# PASSO 8: CLICAR NO CARD "GERENCIAMENTO DE NOTAS"
# Na tela principal do sistema aparecem vários cards.
# Localiza e clica no card de Gerenciamento de Notas.
# ============================================================
async def _abrir_gerenciamento_notas(page: Page) -> bool:
    print("🗂️  [Atende] Procurando card 'Gerenciamento de Notas'...")
    await page.wait_for_timeout(2000)

    seletores = [
        "text=Gerenciamento de Notas",
        "a:has-text('Gerenciamento de Notas')",
        "div:has-text('Gerenciamento de Notas')",
        "button:has-text('Gerenciamento de Notas')",
        "[class*='card']:has-text('Gerenciamento')",
        "text=Gerenciamento",
    ]

    for sel in seletores:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Card clicado: {sel}")
                await page.wait_for_timeout(3000)
                await _screenshot_debug(page, "12_gerenciamento")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Erro ao clicar card ({sel}): {e}")

    print("❌ [Atende] Card 'Gerenciamento de Notas' não encontrado")
    await _screenshot_debug(page, "12_erro_card")
    return False


# ============================================================
# PASSO 9-10: FILTRAR POR COMPETÊNCIA E CONSULTAR
# Seleciona "Competência" no dropdown de filtro e digita
# o período no formato MM/YYYY, depois clica em Consultar.
#
# O formato de data recebido (data_inicio: "01/02/2026") é
# convertido para competência "02/2026" (mês/ano).
# ============================================================
async def _filtrar_competencia_e_consultar(page: Page, data_inicio: str) -> bool:

    # Extrai MM/YYYY da data_inicio (aceita DD/MM/YYYY ou YYYY-MM-DD)
    def extrair_competencia(d: str) -> str:
        if "-" in d and len(d) == 10:          # YYYY-MM-DD
            partes = d.split("-")
            return f"{partes[1]}/{partes[0]}"   # MM/YYYY
        elif "/" in d and len(d) == 10:         # DD/MM/YYYY
            partes = d.split("/")
            return f"{partes[1]}/{partes[2]}"   # MM/YYYY
        return d                                 # já no formato esperado

    competencia = extrair_competencia(data_inicio)
    print(f"📅 [Atende] Filtrando competência: {competencia}")

    await page.wait_for_timeout(2000)

    # ── Seleciona "Competência" no dropdown de filtro ─────────
    seletores_filtro = [
        "select[name*='filtro']",
        "select[id*='filtro']",
        "select[name*='tipo']",
        "select:visible",
    ]

    filtro_selecionado = False
    for sel in seletores_filtro:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                # Tenta selecionar a opção "Competência" pelo texto
                await elem.select_option(label="Competência", timeout=3000)
                print(f"✅ [Atende] 'Competência' selecionada no filtro: {sel}")
                filtro_selecionado = True
                await page.wait_for_timeout(1000)
                break
            except Exception:
                try:
                    # Fallback: seleciona pelo value
                    await elem.select_option(value="competencia", timeout=3000)
                    filtro_selecionado = True
                    break
                except Exception:
                    pass

    if not filtro_selecionado:
        print("⚠️  [Atende] Dropdown de filtro não encontrado — tentando continuar")

    # ── Campo de competência (MM/YYYY) ────────────────────────
    seletores_data = [
        "input[placeholder*='MM/AAAA']",
        "input[placeholder*='mm/aaaa']",
        "input[placeholder*='Competência']",
        "input[placeholder*='competencia']",
        "input[name*='competencia']",
        "input[id*='competencia']",
        "input[name*='data']",
        "input[type='text']:visible",
    ]

    campo_data = None
    for sel in seletores_data:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo competência: {sel}")
            campo_data = elem
            break

    if campo_data:
        await campo_data.scroll_into_view_if_needed()
        await campo_data.triple_click()
        await page.keyboard.type(competencia, delay=80)
        await campo_data.dispatch_event("input")
        await campo_data.dispatch_event("change")
        print(f"✏️  [Atende] Competência digitada: {competencia}")
        await page.wait_for_timeout(1000)
    else:
        print("⚠️  [Atende] Campo de competência não encontrado")

    await _screenshot_debug(page, "13_filtro_preenchido")

    # ── Clica em Consultar ────────────────────────────────────
    seletores_consultar = [
        "button:has-text('Consultar')",
        "button:has-text('Pesquisar')",
        "button:has-text('Buscar')",
        "input[value='Consultar']",
        "input[value='Pesquisar']",
    ]

    for sel in seletores_consultar:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Consultar clicado: {sel}")
                await page.wait_for_timeout(5000)    # aguarda resultados carregarem
                await _screenshot_debug(page, "14_resultados")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Erro Consultar ({sel}): {e}")

    print("❌ [Atende] Botão Consultar não encontrado")
    await _screenshot_debug(page, "14_erro_consultar")
    return False


# ============================================================
# PASSO 11-12: DOWNLOAD TODOS → XML IPM
# Clica em "Download Todos", seleciona "XML IPM" e aguarda
# o arquivo ser baixado. Retorna o caminho do arquivo baixado
# ou None se o download falhar.
# ============================================================
async def _baixar_xml_ipm(page: Page, download_dir: str) -> str | None:
    print("📥 [Atende] Procurando botão 'Download Todos'...")

    seletores_download = [
        "button:has-text('Download Todos')",
        "button:has-text('Download')",
        "a:has-text('Download Todos')",
        "a:has-text('Download')",
        "[class*='download']:has-text('Todos')",
    ]

    btn_download = None
    for sel in seletores_download:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            btn_download = elem
            print(f"✅ [Atende] Botão Download encontrado: {sel}")
            break

    if not btn_download:
        print("❌ [Atende] Botão 'Download Todos' não encontrado")
        await _screenshot_debug(page, "15_erro_download")
        return None

    # Clica no botão Download Todos (abre dropdown com opções)
    await btn_download.click(force=True)
    await page.wait_for_timeout(2000)
    await _screenshot_debug(page, "15_dropdown_download")

    # Seleciona "XML IPM" no dropdown
    seletores_xml_ipm = [
        "text=XML IPM",
        "a:has-text('XML IPM')",
        "button:has-text('XML IPM')",
        "li:has-text('XML IPM')",
        "[class*='option']:has-text('XML IPM')",
        "text=XML",   # fallback se não tiver "IPM" no texto
    ]

    opcao_xml = None
    for sel in seletores_xml_ipm:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            opcao_xml = elem
            print(f"✅ [Atende] Opção XML IPM encontrada: {sel}")
            break

    if not opcao_xml:
        print("❌ [Atende] Opção 'XML IPM' não encontrada no dropdown")
        await _screenshot_debug(page, "15_erro_xml_ipm")
        return None

    # Aguarda o evento de download ao clicar em XML IPM
    print("⏳ [Atende] Iniciando download XML IPM...")
    try:
        async with page.expect_download(timeout=60000) as download_info:
            await opcao_xml.click(force=True)

        download = await download_info.value
        nome_arquivo = download.suggested_filename or "nfse_ipm.zip"
        caminho_destino = os.path.join(download_dir, nome_arquivo)
        await download.save_as(caminho_destino)

        print(f"✅ [Atende] Download concluído: {caminho_destino}")
        return caminho_destino

    except Exception as e:
        print(f"❌ [Atende] Erro no download: {e}")
        await _screenshot_debug(page, "16_erro_download_final")
        return None


# ============================================================
# FUNÇÃO PRINCIPAL: IMPORTAR VIA ATENDE
# Ponto de entrada chamado pela rota /importar-notas-municipal
# em importar.py. Orquestra todo o fluxo de 12 passos acima.
#
# Parâmetros:
#   portal_url   → URL do portal Atende.Net do município
#   usuario      → CPF/CNPJ do contribuinte (usuário do portal)
#   senha        → senha do portal municipal
#   data_inicio  → início do período (DD/MM/YYYY ou YYYY-MM-DD)
#   data_fim     → fim do período (não usado diretamente —
#                  o Atende.Net filtra por competência MM/YYYY)
#
# Retorno:
#   dict com status e caminho do arquivo baixado (ou erro)
# ============================================================
async def importar_via_atende(
    portal_url: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
) -> dict:

    municipio = next(
        (nome for host, nome in PORTAIS_ATENDE.items() if host in portal_url),
        "Município desconhecido"
    )
    print(f"🏙️  [Atende] ═══════════════════════════════════")
    print(f"🏙️  [Atende] Iniciando importação — {municipio}")
    print(f"   Portal    : {portal_url}")
    print(f"   Usuário   : {usuario}")
    print(f"   Período   : {data_inicio} → {data_fim}")
    print(f"   Stealth   : {'✅ ativo' if STEALTH_DISPONIVEL else '❌ inativo'}")
    print(f"🏙️  [Atende] ═══════════════════════════════════")

    # Cria diretório temporário para os downloads
    download_dir = tempfile.mkdtemp(prefix="atende_download_")
    print(f"📁 [Atende] Diretório de download: {download_dir}")

    p, browser, context, page = await criar_browser_atende(download_dir)

    try:
        # ── Passo 1-3: Login ──────────────────────────────────
        login_ok = await _fazer_login(page, portal_url, usuario, senha)
        if not login_ok:
            raise Exception(
                f"Falha no login em {portal_url}. "
                f"Verifique usuário/senha. "
                f"Consulte logs /tmp/atende_debug_*.png para diagnóstico."
            )

        # ── Passo 4: Botão Acessar intermediário ──────────────
        await _clicar_acessar(page)

        # ── Passo 5: Captcha ──────────────────────────────────
        captcha_ok = await _resolver_captcha(page)
        if not captcha_ok:
            raise Exception(
                "Captcha com desafio de imagens detectado — resolução automática indisponível. "
                "Verifique os logs e considere integrar serviço 2captcha."
            )

        # ── Passos 6-7: Aguardar sistema e fechar popup ───────
        await _aguardar_sistema_e_fechar_popup(page)

        # ── Passo 8: Card Gerenciamento de Notas ──────────────
        gerenc_ok = await _abrir_gerenciamento_notas(page)
        if not gerenc_ok:
            raise Exception(
                "Card 'Gerenciamento de Notas' não encontrado. "
                "Verifique screenshot /tmp/atende_debug_12_erro_card_*.png"
            )

        # ── Passos 9-10: Filtrar competência e consultar ──────
        filtro_ok = await _filtrar_competencia_e_consultar(page, data_inicio)
        if not filtro_ok:
            raise Exception(
                "Não foi possível aplicar o filtro de competência. "
                "Verifique screenshot /tmp/atende_debug_14_erro_consultar_*.png"
            )

        # ── Passos 11-12: Download XML IPM ────────────────────
        caminho_arquivo = await _baixar_xml_ipm(page, download_dir)
        if not caminho_arquivo:
            raise Exception(
                "Falha no download do XML IPM. "
                "Verifique screenshot /tmp/atende_debug_15_*.png"
            )

        print(f"🏁 [Atende] ✅ Importação concluída: {caminho_arquivo}")

        # Retorna metadados do arquivo para o importar.py processar
        return {
            "status": "concluido",
            "municipio": municipio,
            "arquivo": caminho_arquivo,
            "nome_arquivo": os.path.basename(caminho_arquivo),
            "tamanho_bytes": os.path.getsize(caminho_arquivo),
            "competencia": data_inicio,
        }

    finally:
        # Fecha o browser SEMPRE, mesmo em caso de exceção
        await fechar_browser_atende(p, browser)
