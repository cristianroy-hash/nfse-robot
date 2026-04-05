import os
import tempfile
import traceback
from app.robot.browser import criar_browser_com_certificado
from app.robot.login_cert import login_certificado
from app.robot.consultar import consultar_notas, baixar_xml
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def salvar_no_supabase(client_id: str, competencia: str, numero: str, caminho_local: str):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        caminho_storage = f"{client_id}/{competencia}/{numero}.xml"
        with open(caminho_local, "rb") as f:
            conteudo = f.read()
        supabase.storage.from_("invoices").upload(
            path=caminho_storage,
            file=conteudo,
            file_options={"content-type": "application/xml", "upsert": "true"}
        )
        print(f"Salvo no Supabase: {caminho_storage}")
        return caminho_storage
    except Exception as e:
        print(f"Erro Supabase: {str(e)}")
        return None

def executar_importacao(job_id: str, payload: dict, jobs: dict):
    p = None
    browser = None
    cert_path = None
    key_path = None
    tmp_dir = tempfile.mkdtemp()

    try:
        jobs[job_id]["status"] = "running"
        print(f"Job {job_id} iniciado")

        p, browser, context, page, cert_path, key_path = criar_browser_com_certificado(
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        login_certificado(page)
        notas = consultar_notas(page, payload["competencia"])
        jobs[job_id]["notas_encontradas"] = len(notas)

        xmls_baixados = 0
        for nota in notas:
            try:
                sucesso = baixar_xml(page, nota, tmp_dir)
                if sucesso:
                    caminho_local = os.path.join(tmp_dir, f"{nota['numero']}.xml")
                    if os.path.exists(caminho_local) and SUPABASE_URL and SUPABASE_KEY:
                        salvar_no_supabase(
                            payload["cliente_id"],
                            payload["competencia"],
                            nota["numero"],
                            caminho_local
                        )
                    xmls_baixados += 1
                    jobs[job_id]["notas_importadas"] = xmls_baixados
            except Exception as e:
                print(f"Erro na nota {nota['numero']}: {str(e)}")
                continue

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"{xmls_baixados} notas importadas"
        print(f"Job {job_id} concluído — {xmls_baixados} notas")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)
        print(f"Job {job_id} falhou: {traceback.format_exc()}")

    finally:
        if browser:
            browser.close()
        if p:
            p.stop()
        if cert_path and os.path.exists(cert_path):
            os.remove(cert_path)
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
