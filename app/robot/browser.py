from playwright.sync_api import sync_playwright

def criar_browser():
    p = sync_playwright().start()
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage"
        ]
    )
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(60000)
    return p, browser, context, page
