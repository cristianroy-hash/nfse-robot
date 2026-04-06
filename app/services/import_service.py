import os
import tempfile
import traceback
import shutil

from app.robot.browser import criar_browser_com_certificado
from app.robot.consultar import consultar_notas, baixar_xml
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def salvar_no_supabase(client_id: str, periodo: str, numero: str, caminho_local: str):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

        caminho_storage = f"{client_id}/{periodo}/{numero}.xml"

        with open(caminho_local, "rb") as f:
            conteudo = f.read()

        supabase.storage.from_("invoices").upload(
            path=caminho_storage,
            file=conteudo,
            file_options={"content-type": "application/xml", "upsert": "true"}
        )

        # ADICIONE ESTA LINHA PARA GERAR A URL PÚBLICA
        url_publica = supabase.storage.from_("invoices").get_public_url(caminho_storage)

        print(f"Salvo no Supabase: {caminho_storage}")
        return caminho_storage

    except Exception as e:
        print(f"Erro Supabase: {str(e)}")
        return None


async def executar_importacao(job_id: str, payload: dict, jobs: dict):
    p = None
    browser = None
    context = None
    page = None
    cert_path = None
    key_path = None

    tmp_dir = tempfile.mkdtemp()

    try:
        jobs[job_id]["status"] = "running"
        print(f"🚀 Job {job_id} iniciado")

        data_inicio = payload.get("data_inicio")
        data_fim = payload.get("data_fim")
        periodo_str = f"{data_inicio}_{data_fim}"

        # =========================
        # BROWSER + CERTIFICADO
        # =========================
        print("🔐 Inicializando browser com certificado...")

        p, browser, context, page, cert_path, key_path = await criar_browser_com_certificado(
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        print("🌐 Browser criado, iniciando consulta...")

        # =========================
        # CONSULTA
        # =========================
        notas = await consultar_notas(page, data_inicio, data_fim)

        # 🔥 PROTEÇÃO (ESSENCIAL)
        if not notas or not isinstance(notas, list):
            raise Exception(f"❌ Consulta não retornou lista válida: {type(notas)}")

        jobs[job_id]["notas_encontradas"] = len(notas)

        xmls_baixados = 0

        # =========================
        # DOWNLOAD
        # =========================
        for nota in notas:
            try:
                sucesso = await baixar_xml(page, nota, tmp_dir)

                if sucesso:
                    arquivos = [f for f in os.listdir(tmp_dir) if f.endswith(".xml")]

                    for nome_arquivo in arquivos:
                        caminho_local = os.path.join(tmp_dir, nome_arquivo)

                        # --- INÍCIO DA ADIÇÃO ---
                        # Lemos o texto do XML para enviar direto ao HTML (resolve o problema do ZIP vazio)
                        with open(caminho_local, "r", encoding="utf-8") as f:
                        nota["conteudo_xml"] = f.read()  # NOVO: Guarda o texto do XML na nota
                        # --- FIM DA ADIÇÃO ---

                        if SUPABASE_URL and SUPABASE_KEY:
                            # CAPTURE A URL RETORNADA AQUI
                            nova_url = salvar_no_supabase(                    
                                payload["cliente_id"],
                                periodo_str,
                                nome_arquivo.replace(".xml", ""),
                                caminho_local
                            )
                            # ATUALIZE A URL NA NOTA PARA O HTML USAR
                            if nova_url:
                                nota["url_download"] = nova_url

                        os.remove(caminho_local)

                        xmls_baixados += 1
                        jobs[job_id]["notas_importadas"] = xmls_baixados

            except Exception as e:
                print(f"Erro na nota: {str(e)}")
                continue

        # ESTA LINHA É CRÍTICA: Envie a lista preenchida para o Job
        jobs[job_id]["notas"] = notas
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"{xmls_baixados} notas importadas"

        print(f"✅ Job finalizado — {xmls_baixados} notas")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)

        print(f"❌ Job falhou: {traceback.format_exc()}")

    finally:
        try:
            if browser:
                await browser.close()
            if p:
                await p.stop()
            if cert_path and os.path.exists(cert_path):
                os.remove(cert_path)
            if key_path and os.path.exists(key_path):
                os.remove(key_path)
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

            print("🧹 Limpeza final concluída")

        except Exception as e:
            print(f"Erro limpeza: {str(e)}")


