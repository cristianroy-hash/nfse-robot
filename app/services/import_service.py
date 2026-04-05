import os
import tempfile
import traceback
# Importante garantir que o criar_browser_com_certificado aceite os parâmetros corretos
from app.robot.browser import criar_browser_com_certificado
from app.robot.login_cert import login_certificado
from app.robot.consultar import consultar_notas, baixar_xml

def executar_importacao(job_id: str, payload: dict, jobs: dict):
    p = None
    browser = None
    context = None
    page = None
    cert_path = None
    
    # Criamos um diretório temporário para salvar o PFX físico
    tmp_dir = tempfile.mkdtemp()

    try:
        jobs[job_id]["status"] = "running"
        print(f"Job {job_id} iniciado")

        # ATENÇÃO: Verifique se sua função criar_browser_com_certificado 
        # está configurando o 'client_certificates' no browser.new_context
        p, browser, context, page, cert_path = criar_browser_com_certificado(
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        # Realiza o login
        login_certificado(page)

        # Restante do fluxo
        notas = consultar_notas(page, payload["competencia"])
        jobs[job_id]["notas_encontradas"] = len(notas)

        xmls_baixados = 0
        for nota in notas:
            try:
                # Passamos o contexto ou a página conforme sua implementação
                baixar_xml(page, nota, tmp_dir)
                xmls_baixados += 1
                jobs[job_id]["notas_importadas"] = xmls_baixados
                print(f"XML baixado: {nota['numero']}")
            except Exception as e:
                print(f"Erro na nota {nota['numero']}: {str(e)}")
                continue

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"{xmls_baixados} notas importadas com sucesso"

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        # Captura o erro real para o painel
        jobs[job_id]["message"] = str(e)
        print(f"Job {job_id} falhou: {traceback.format_exc()}")

    finally:
        # Fechamento seguro
        if browser:
            browser.close()
        if p:
            p.stop()
        # Limpeza do arquivo PFX temporário
        if cert_path and os.path.exists(cert_path):
            try:
                os.remove(cert_path)
            except:
                pass
