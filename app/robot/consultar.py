import os
import re

def consultar_notas(page, data_inicio: str, data_fim: str):
    try:
        print(f"Período: {data_inicio} a {data_fim}")

        # Está no Dashboard — vamos expandir o menu hamburguer
        print("Expandindo menu de navegação...")
        try:
            page.locator(".navbar-toggle, button[data-toggle='collapse']").first.click()
            page.wait_for_timeout(2000)
        except:
            print("Menu toggle não encontrado, continuando...")

        # Captura todos os links após expandir menu
        links = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a'))
                .map(a => ({ text: a.innerText.trim(), href: a.href }))
                .filter(a => a.text && a.href);
        }""")
        print(f"Links após expandir menu: {links}")

        # Procura link de consulta/notas emitidas
        url_notas = None
        termos = ["emitida", "consultar", "nfse", "nota", "rascunho"]
        for link in links:
            texto = link["text"].lower()
            href = link["href"].lower()
            if any(t in texto or t in href for t in termos):
                url_notas = link["href"]
                print(f"Link de notas encontrado: {url_notas}")
                break

        if not url_notas:
            print("Nenhum link de notas encontrado. Links disponíveis:")
            for l in links:
                print(f"  {l}")
            return []

        # Navega para a página de notas
        page.goto(url_notas, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        url_atual = page.url
        texto = page.evaluate("() => document.body.innerText.substring(0, 1000)")
        inputs = page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input')).map(i => ({
                id: i.id, name: i.name, type: i.type,
                class: i.className, placeholder: i.placeholder
            }))
        }""")
        print(f"URL notas: {url_atual}")
        print(f"Texto: {texto}")
        print(f"Inputs: {inputs}")

        return []

    except Exception as e:
        page.screenshot(path="/tmp/erro_consulta.png")
        raise Exception(f"Erro na consulta: {str(e)}")

def baixar_xml(page, nota: dict, download_dir: str):
    return False
