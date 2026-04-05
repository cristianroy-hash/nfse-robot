import os
import tempfile
import traceback
from app.robot.browser import criar_browser_com_certificado
from app.robot.login_cert import login_certificado
from app.robot.consultar import consultar_notas, baixar_xml
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def salvar_no_supabase(client_id: str, periodo: str, numero: str, caminho_local: str):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # O caminho no storage agora usa o período (ex: 2026-03-01_2026-03-31)
        caminho_storage = f"{client_id}/{periodo}/{numero}.xml"
        
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

        # Extração segura dos novos campos
        data_inicio = payload.get("data_inicio")
        data_fim = payload.get("data_fim")
        # Criamos uma string de período para organizar as pastas no Supabase
        periodo_str = f"{data_inicio}_{data_fim}"

        p, browser, context, page, cert_path, key_path = criar_browser_com_certificado(
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        login_certificado(page)
        
        # Chamada ao robô atualizada para aceitar o período ou data inicial
        # Se o seu consultar_notas espera apenas uma string, passamos data_inicio
        # Se ele já foi atualizado para dois parâmetros, ajuste aqui:
        notas = await consultar_notas(page, data_inicio, data_fim) 
        
        jobs[job_id]["notas_encontradas"] = len(notas)

        xmls_baixados = 0
        for nota in notas:
            try:
                # O baixar_xml salvará o arquivo no diretório temporário
                sucesso = await baixar_xml(page, nota, tmp_dir)
                
                if sucesso:
                    # O robô agora salva com o ID da nota como nome do arquivo
                    # Tentamos localizar o arquivo XML gerado no tmp_dir
                    arquivos = [f for f in os.listdir(tmp_dir) if f.endswith(".xml")]
                    if arquivos:
                        # Pegamos o último arquivo baixado (ou o que corresponda à nota atual)
                        ultimo_xml = arquivos[-1]
                        caminho_local = os.path.join(tmp_dir, ultimo_xml)
                        
                        if SUPABASE_URL and SUPABASE_KEY:
                            salvar_no_supabase(
                                payload["cliente_id"],
                                periodo_str,
                                ultimo_xml.replace(".xml", ""),
                                caminho_local
                            )
                        
                        # Removemos do local após subir para não confundir o próximo loop
                        os.remove(caminho_local)
                        
                    xmls_baixados += 1
                    jobs[job_id]["notas_importadas"] = xmls_baixados
                    
            except Exception as e:
                print(f"Erro no processamento da nota: {str(e)}")
                continue

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"{xmls_baixados} notas importadas com sucesso"
        print(f"Job {job_id} concluído — {xmls_baixados} notas")

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)
        print(f"Job {job_id} falhou: {traceback.format_exc()}")

    finally:
        # Limpeza de recursos
        if browser:
            browser.close()
        if p:
            p.stop()
        if cert_path and os.path.exists(cert_path):
            os.remove(cert_path)
        if key_path and os.path.exists(key_path):
            os.remove(key_path)
