from app.robot.browser import criar_browser
from app.robot.login_cert import login_certificado
from app.robot.consultar import consultar_notas, baixar_xml
import traceback

def executar_importacao(payload: dict):
    p = None
    browser = None
    
    try:
        p, browser, context, page = criar_browser()

        # Login com certificado
        login_certificado(
            page,
            context,
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        # Consulta notas
        notas = consultar_notas(page, payload["competencia"])

        # Baixa XMLs
        xmls = []
        for nota in notas:
            try:
                xml = baixar_xml(page, nota)
                xmls.append({
                    "numero": nota["numero"],
                    "xml": xml
                })
            except Exception as e:
                print(f"Erro na nota {nota['numero']}: {str(e)}")
                continue

        return {
            "status": "completed",
            "cliente_id": payload["cliente_id"],
            "competencia": payload["competencia"],
            "notas_importadas": len(xmls),
            "notas": xmls
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "detail": traceback.format_exc()
        }

    finally:
        if browser:
            browser.close()
        if p:
            p.stop()
