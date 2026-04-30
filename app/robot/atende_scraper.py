# ============================================================
# [NOVO v2] app/robot/atende_scraper.py
#
# Scraper Playwright para portais municipais baseados no
# sistema Atende.Net. Adicionado no robô v2 para suporte aos
# municípios de São José/SC, Palhoça/SC e Biguaçu/SC.
#
# Fluxo real mapeado (29/04/2026):
#   1. Acessa o portal municipal (portal_url)
#   2. Preenche usuário (CPF/CNPJ) e senha
#   3. Clica em Entrar
#   4. Tela intermediária com botão "Acessar" → clica
#   5. Tela de captcha "Não sou robô" → stealth passa automaticamente
#   6. Redireciona para https://nfse-*.atende.net/?rot=1#!/sistema/66
#   7. Fecha popup de aviso (se existir)
#   8. Clica no card "Gerenciamento de Notas"
#   9. Seleciona "Competência" no filtro e digita MM/YYYY
#  10. Clica em "Consultar"
#  11. Clica em "Download Todos" → seleciona "XML IPM"
#  12. Aguarda download e retorna metadados do arquivo
#
# CORREÇÃO v2.3 (30/04/2026) — erro de API do stealth:
#   Mensagem: "object AsyncWrappingContextManager can't be used in 'await'"
#   Causa: código usava `await Stealth().use_async(page)` que mistura
#   a API v2.x (context manager com async with) com a v1.x (coroutine).
#   Solução: usar `await stealth_async(page)` — API correta do pacote
#   playwright-stealth v1.x (AtuboDad), aplicada direto na page depois
#   de new_page() e antes do primeiro goto().
#
#   APIs e quando usar cada uma:
#     await stealth_async(page)                    ← v1.x ✅ USADA AQUI
#     async with Stealth().use_async(playwright()) ← v2.x (exige refactor)
#
# Dependência adicionada ao requirements.txt:
#   playwright-stealth==1.0.6
# ============================================================

import os
import asyncio
import tempfile
from datetime import datetime
from playwright.async_api import async_playwright, Page

# ============================================================
# STEALTH — API CORRETA v1.x (playwright-stealth AtuboDad)
# Uso: await stealth_async(page)
# Aplicado depois de new_page() e ANTES do primeiro goto().
# Fallback seguro: se não instalado o robô continua funcionando
# (mas o captcha pode bloquear sem o stealth).
# ============================================================
try:
    from playwright_stealth import stealth_async
    STEALTH_DISPONIVEL = True
    print("✅ [Atende] playwright-stealth carregado (stealth_async v1.x)")
except ImportError:
    STEALTH_DISPONIVEL = False
    print("⚠️  [Atende] playwright-stealth não instalado — captcha pode bloquear")


# ============================================================
# MAPEAMENTO DE PORTAIS ATENDE.NET SUPORTADOS
# Para adicionar novos municípios: inclua uma nova entrada aqui.
# ============================================================
PORTAIS_ATENDE = {
    "nfse-saojose.atende.net": "São José/SC",
    "nfse-palhoca.atende.net": "Palhoça/SC",
    "nfse-bigua.atende.net":   "Biguaçu/SC",
}


# ============================================================
# VERIFICADOR: IS_PORTAL_ATENDE
# Retorna True se a URL pertence a um portal Atende.Net suportado.
# Chamado em importar.py para validar portal_url antes de chamar
# importar_via_atende().
# ============================================================
def is_portal_atende(portal_url: str) -> bool:
    if not portal_url:
        return False
    return any(host in portal_url for host in PORTAIS_ATENDE)


# ============================================================
# HELPER: SCREENSHOT DE DEBUG
# Salva screenshot em /tmp — visível nos logs do Railway.
# Útil para identificar em qual etapa o scraper travou.
# ============================================================
async def _screenshot_debug(page: Page, nome: str):
    try:
        caminho = f"/tmp/atende_debug_{nome}_{datetime.now().strftime('%H%M%S')}.png"
        await page.screenshot(path=caminho, full_page=True)
        print(f"📸 [Atende] Screenshot: {caminho}")
    except Exception as e:
        print(f"⚠️  [Atende] Screenshot falhou ({nome}): {e}")


# ============================================================
# CRIAR BROWSER COM STEALTH
# Cria o browser e aplica stealth_async na page.
# IMPORTANTE: stealth_async(page) deve ser chamado DEPOIS de
# new_page() e ANTES do primeiro goto().
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
        viewport={"width": 1366, "height": 768},
        ignore_https_errors=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        accept_downloads=True,
    )

    page = await context.new_page()
    page.set_default_timeout(60000)

    # CORREÇÃO v2.3: API correta — await stealth_async(page)
    # aplicado antes do primeiro goto() para injetar patches JS
    if STEALTH_DISPONIVEL:
        await stealth_async(page)
        print("🥷 [Atende] stealth_async aplicado")

    print("🌐 [Atende] Browser pronto")
    return p, browser, context, page


# ============================================================
# FECHAR BROWSER — sempre no bloco finally
# ============================================================
async def fechar_browser_atende(p, browser):
    try:
        await browser.close()
        await p.stop()
        print("🔒 [Atende] Browser fechado")
    except Exception as e:
        print(f"⚠️  [Atende] Erro ao fechar browser: {e}")


# ============================================================
# PASSO 1-3: LOGIN
# Preenche usuário/senha e clica em Entrar.
# keyboard.type com delay=80ms dispara eventos individuais que
# o web component do Atende.Net precisa para habilitar o botão.
# ============================================================
async def _fazer_login(page: Page, portal_url: str, usuario: str, senha: str) -> bool:
    print(f"🌐 [Atende] Acessando: {portal_url}")
    await page.goto(portal_url, wait_until="networkidle", timeout=90000)
    await page.wait_for_timeout(3000)
    await _screenshot_debug(page, "01_pagina_inicial")

    # ── Campo usuário ─────────────────────────────────────────
    seletores_usuario = [
        "input[name='login']", "input[id='login']",
        "input[name='usuario']", "input[id='usuario']",
        "input[type='text']:visible",
    ]
    campo_usuario = None
    for sel in seletores_usuario:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            print(f"✅ [Atende] Campo usuário: {sel}")
            campo_usuario = elem
            break

    if not campo_usuario:
        print("❌ [Atende] Campo usuário não encontrado")
        await _screenshot_debug(page, "02_erro_usuario")
        return False

    await campo_usuario.scroll_into_view_if_needed()
    await campo_usuario.click()
    await page.keyboard.type(usuario, delay=80)
    await campo_usuario.dispatch_event("input")
    await campo_usuario.dispatch_event("change")
    print("✏️  [Atende] Usuário digitado")
    await page.wait_for_timeout(1200)

    # ── Campo senha ───────────────────────────────────────────
    seletores_senha = [
        "input[name='senha']", "input[id='senha']",
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
        print("❌ [Atende] Campo senha não encontrado")
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

    # Remove CSS que oculta o botão antes de clicar
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

    # ── Clicar em Entrar — 3 estratégias ─────────────────────
    btn_clicado = False

    # Estratégia 1: force=True
    for sel in ["button[name='btn_entrar']", "button[type='submit']",
                "input[type='submit']", "button:has-text('Entrar')"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Entrar clicado (force): {sel}")
                btn_clicado = True
                break
            except Exception as e:
                print(f"⚠️  [Atende] force=True falhou ({sel}): {e}")

    # Estratégia 2: JS click
    if not btn_clicado:
        try:
            clicou = await page.evaluate("""
                () => {
                    let b = document.querySelector("button[name='btn_entrar']")
                         || document.querySelector("button[type='submit']")
                         || Array.from(document.querySelectorAll('button'))
                                .find(x => ['Entrar','Acessar'].includes(x.textContent.trim()));
                    if (b) { b.click(); return true; }
                    return false;
                }
            """)
            if clicou:
                print("✅ [Atende] Entrar clicado via JS")
                btn_clicado = True
        except Exception as e:
            print(f"⚠️  [Atende] JS click falhou: {e}")

    # Estratégia 3: Enter
    if not btn_clicado:
        try:
            await campo_senha.press("Enter")
            print("✅ [Atende] Enter no campo senha")
            btn_clicado = True
        except Exception as e:
            print(f"⚠️  [Atende] Enter falhou: {e}")

    if not btn_clicado:
        await _screenshot_debug(page, "05_erro_botao")
        return False

    await page.wait_for_timeout(4000)
    await _screenshot_debug(page, "06_pos_entrar")

    url_atual = page.url
    if "login" in url_atual.lower():
        print(f"❌ [Atende] Ainda na página de login: {url_atual}")
        return False

    print(f"✅ [Atende] Login ok — URL: {url_atual}")
    return True


# ============================================================
# PASSO 4: BOTÃO "ACESSAR" INTERMEDIÁRIO
# ============================================================
async def _clicar_acessar(page: Page):
    print("🖱️  [Atende] Procurando botão Acessar...")
    await page.wait_for_timeout(2000)

    for sel in ["button:has-text('Acessar')", "a:has-text('Acessar')",
                "input[value='Acessar']", "button:has-text('Continuar')"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Acessar clicado: {sel}")
                await page.wait_for_timeout(3000)
                await _screenshot_debug(page, "07_pos_acessar")
                return
            except Exception as e:
                print(f"⚠️  [Atende] Acessar falhou ({sel}): {e}")

    print("ℹ️   [Atende] Botão Acessar não encontrado — continuando")


# ============================================================
# PASSO 5: CAPTCHA
# Com stealth ativo, o captcha comportamental passa automaticamente.
# Tenta clicar no checkbox se aparecer.
# ============================================================
async def _resolver_captcha(page: Page) -> bool:
    print("🤖 [Atende] Verificando captcha...")
    await page.wait_for_timeout(3000)
    await _screenshot_debug(page, "08_captcha_check")

    if await page.locator("iframe[src*='recaptcha']").count() == 0:
        print("✅ [Atende] Sem captcha — stealth funcionou!")
        return True

    try:
        iframe = page.frame_locator("iframe[src*='recaptcha']").first
        checkbox = iframe.locator("#recaptcha-anchor").first
        if await checkbox.count() > 0:
            await checkbox.click(timeout=10000)
            await page.wait_for_timeout(4000)
            await _screenshot_debug(page, "09_pos_captcha")

            if await page.locator("iframe[src*='bframe']").count() > 0:
                print("❌ [Atende] Captcha de imagens — resolução automática indisponível")
                return False

            print("✅ [Atende] Captcha resolvido com clique")
            return True
    except Exception as e:
        print(f"⚠️  [Atende] Erro no captcha: {e}")

    print("✅ [Atende] Continuando após captcha")
    return True


# ============================================================
# PASSO 6-7: AGUARDAR SISTEMA E FECHAR POPUP
# ============================================================
async def _aguardar_sistema_e_fechar_popup(page: Page):
    print("⏳ [Atende] Aguardando sistema...")
    try:
        await page.wait_for_url("**/sistema/**", timeout=30000)
        print(f"✅ [Atende] Sistema: {page.url}")
    except Exception:
        print(f"⚠️  [Atende] Timeout — URL: {page.url}")

    await page.wait_for_timeout(3000)
    await _screenshot_debug(page, "10_sistema")

    for sel in ["button:has-text('Fechar')", "button:has-text('OK')",
                "button:has-text('Entendido')", "button:has-text('×')",
                "[aria-label='Close']", "[aria-label='Fechar']"]:
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
# PASSO 8: CARD "GERENCIAMENTO DE NOTAS"
# ============================================================
async def _abrir_gerenciamento_notas(page: Page) -> bool:
    print("🗂️  [Atende] Procurando card 'Gerenciamento de Notas'...")
    await page.wait_for_timeout(2000)

    for sel in ["text=Gerenciamento de Notas",
                "a:has-text('Gerenciamento de Notas')",
                "div:has-text('Gerenciamento de Notas')",
                "[class*='card']:has-text('Gerenciamento')",
                "text=Gerenciamento"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Card clicado: {sel}")
                await page.wait_for_timeout(3000)
                await _screenshot_debug(page, "12_gerenciamento")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Card falhou ({sel}): {e}")

    print("❌ [Atende] Card não encontrado")
    await _screenshot_debug(page, "12_erro_card")
    return False


# ============================================================
# PASSO 9-10: FILTRO COMPETÊNCIA + CONSULTAR
# data_inicio "01/02/2026" → competência "02/2026"
# ============================================================
async def _filtrar_competencia_e_consultar(page: Page, data_inicio: str) -> bool:

    def extrair_competencia(d: str) -> str:
        if "-" in d and len(d) == 10:       # YYYY-MM-DD
            p = d.split("-")
            return f"{p[1]}/{p[0]}"
        elif "/" in d and len(d) == 10:     # DD/MM/YYYY
            p = d.split("/")
            return f"{p[1]}/{p[2]}"
        return d

    competencia = extrair_competencia(data_inicio)
    print(f"📅 [Atende] Competência: {competencia}")
    await page.wait_for_timeout(2000)

    # Seleciona "Competência" no dropdown
    for sel in ["select[name*='filtro']", "select[id*='filtro']",
                "select[name*='tipo']", "select:visible"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.select_option(label="Competência", timeout=3000)
                print(f"✅ [Atende] Competência selecionada: {sel}")
                await page.wait_for_timeout(1000)
                break
            except Exception:
                try:
                    await elem.select_option(value="competencia", timeout=3000)
                    break
                except Exception:
                    pass

    # Campo de data MM/YYYY
    campo_data = None
    for sel in ["input[placeholder*='MM/AAAA']", "input[placeholder*='mm/aaaa']",
                "input[placeholder*='ompet']", "input[name*='competencia']",
                "input[id*='competencia']", "input[name*='data']",
                "input[type='text']:visible"]:
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
        print(f"✏️  [Atende] Competência: {competencia}")
        await page.wait_for_timeout(1000)
    else:
        print("⚠️  [Atende] Campo de competência não encontrado")

    await _screenshot_debug(page, "13_filtro_preenchido")

    # Clica em Consultar
    for sel in ["button:has-text('Consultar')", "button:has-text('Pesquisar')",
                "button:has-text('Buscar')", "input[value='Consultar']"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            try:
                await elem.click(force=True, timeout=5000)
                print(f"✅ [Atende] Consultar: {sel}")
                await page.wait_for_timeout(5000)
                await _screenshot_debug(page, "14_resultados")
                return True
            except Exception as e:
                print(f"⚠️  [Atende] Consultar falhou ({sel}): {e}")

    print("❌ [Atende] Botão Consultar não encontrado")
    await _screenshot_debug(page, "14_erro_consultar")
    return False


# ============================================================
# PASSO 11-12: DOWNLOAD TODOS → XML IPM
# ============================================================
async def _baixar_xml_ipm(page: Page, download_dir: str):
    print("📥 [Atende] Procurando 'Download Todos'...")

    btn_download = None
    for sel in ["button:has-text('Download Todos')", "button:has-text('Download')",
                "a:has-text('Download Todos')", "a:has-text('Download')"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            btn_download = elem
            print(f"✅ [Atende] Botão Download: {sel}")
            break

    if not btn_download:
        print("❌ [Atende] Botão Download não encontrado")
        await _screenshot_debug(page, "15_erro_download")
        return None

    await btn_download.click(force=True)
    await page.wait_for_timeout(2000)
    await _screenshot_debug(page, "15_dropdown_download")

    opcao_xml = None
    for sel in ["text=XML IPM", "a:has-text('XML IPM')",
                "button:has-text('XML IPM')", "li:has-text('XML IPM')", "text=XML"]:
        elem = page.locator(sel).first
        if await elem.count() > 0:
            opcao_xml = elem
            print(f"✅ [Atende] XML IPM: {sel}")
            break

    if not opcao_xml:
        print("❌ [Atende] Opção XML IPM não encontrada")
        await _screenshot_debug(page, "15_erro_xml_ipm")
        return None

    print("⏳ [Atende] Aguardando download...")
    try:
        async with page.expect_download(timeout=60000) as download_info:
            await opcao_xml.click(force=True)

        download = await download_info.value
        nome_arquivo = download.suggested_filename or "nfse_ipm.zip"
        caminho_destino = os.path.join(download_dir, nome_arquivo)
        await download.save_as(caminho_destino)
        print(f"✅ [Atende] Download: {caminho_destino}")
        return caminho_destino

    except Exception as e:
        print(f"❌ [Atende] Erro no download: {e}")
        await _screenshot_debug(page, "16_erro_download")
        return None


# ============================================================
# FUNÇÃO PRINCIPAL: IMPORTAR VIA ATENDE
# Ponto de entrada chamado por POST /importar-notas-municipal
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
    print(f"🏙️  [Atende] ══════════════════════════════════")
    print(f"🏙️  [Atende] {municipio} | {data_inicio} → {data_fim}")
    print(f"   Stealth: {'✅ ativo' if STEALTH_DISPONIVEL else '❌ inativo'}")
    print(f"🏙️  [Atende] ══════════════════════════════════")

    download_dir = tempfile.mkdtemp(prefix="atende_download_")
    p, browser, context, page = await criar_browser_atende()

    try:
        # 1-3: Login
        if not await _fazer_login(page, portal_url, usuario, senha):
            raise Exception(
                f"Falha no login em {portal_url}. Verifique usuário/senha. "
                "Veja logs /tmp/atende_debug_*.png no Railway."
            )

        # 4: Acessar
        await _clicar_acessar(page)

        # 5: Captcha
        if not await _resolver_captcha(page):
            raise Exception(
                "Captcha de imagens detectado — resolução automática indisponível."
            )

        # 6-7: Sistema + popup
        await _aguardar_sistema_e_fechar_popup(page)

        # 8: Card
        if not await _abrir_gerenciamento_notas(page):
            raise Exception(
                "Card 'Gerenciamento de Notas' não encontrado. "
                "Veja /tmp/atende_debug_12_erro_card_*.png"
            )

        # 9-10: Filtro + Consultar
        if not await _filtrar_competencia_e_consultar(page, data_inicio):
            raise Exception(
                "Filtro de competência falhou. "
                "Veja /tmp/atende_debug_14_erro_consultar_*.png"
            )

        # 11-12: Download XML IPM
        caminho_arquivo = await _baixar_xml_ipm(page, download_dir)
        if not caminho_arquivo:
            raise Exception(
                "Download XML IPM falhou. Veja /tmp/atende_debug_15_*.png"
            )

        print(f"🏁 [Atende] ✅ Concluído: {caminho_arquivo}")
        return {
            "status": "concluido",
            "municipio": municipio,
            "arquivo": caminho_arquivo,
            "nome_arquivo": os.path.basename(caminho_arquivo),
            "tamanho_bytes": os.path.getsize(caminho_arquivo),
            "competencia": data_inicio,
        }

    finally:
        await fechar_browser_atende(p, browser)
