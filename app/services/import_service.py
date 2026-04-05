import os
import tempfile
import traceback
import asyncio  # Importante para garantir suporte a async se necessário
from app.robot.browser import criar_browser_com_certificado
from app.robot.login_cert import login_certificado
from app.robot.consultar import consultar_notas, baixar_xml
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def salvar_no_supabase(client_id: str, periodo: str, numero: str, caminho_local: str):
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Organização: invoices/ID_CLIENTE/DATA_INICIO_DATA_FIM/NUMERO.xml
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

# ALTERAÇÃO CRÍTICA: Adicionado 'async' antes de 'def'
async def executar_importacao(job_id: str, payload: dict, jobs: dict):
    p = None
    browser = None
    cert_path = None
    key_path = None
    tmp_dir = tempfile.mkdtemp()

    try:
        jobs[job_id]["status"] = "running"
        print(f"Job {job_id} iniciado")

        data_inicio = payload.get("data_inicio")
        data_fim = payload.get("data_fim")
        periodo_str = f"{data_inicio}_{data_fim}"

        # Se criar_browser_com_certificado for síncrono, mantenha assim. 
        # Se for assíncrono, adicione await.
        p, browser, context, page, cert_path, key_path = criar_browser_com_certificado(
            payload["certificado_base64"],
            payload["certificado_senha"]
        )

        # Se login_certificado for async, adicione await login_certificado(page)
        login_certificado(page)
        
        # AGORA FUNCIONARÁ: Esperando a corrotina das notas
        notas = await consultar_notas(page, data_inicio, data_fim) 
        
        jobs[job_id]["notas_encontradas"] = len(notas)
        xmls_baixados = 0

        for nota in notas:
            try:
                # O baixar_xml salvará o arquivo no diretório temporário
                # Usamos await pois alteramos o consultar.py para async
                sucesso = await baixar_xml(page, nota, tmp_dir)
                
                if sucesso:
                    # Melhoria: Buscar o arquivo específico que acabou de ser baixado
                    # O robô usa a chave_acesso ou data_chave como nome
                    arquivos = [f for f in os.listdir(tmp_dir) if f.endswith(".xml")]
                    
                    if arquivos:
                        # Pegamos o arquivo mais recente ou o único na pasta
                        nome_arquivo = arquivos[0] 
                        caminho_local = os.path.join(tmp_dir, nome_arquivo)
                        
                        if SUPABASE_URL and SUPABASE_KEY:
                            salvar_no_supabase(
                                payload["cliente_id"],
                                periodo_str,
                                nome_arquivo.replace(".xml", ""),
                                caminho_local
                            )
                        
                        # Limpeza imediata para não acumular arquivos no container
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
        # Limpeza robusta
        try:
            if browser:
                # Se fechar o browser for async no seu setup: await browser.close()
                browser.close()
            if p:
                p.stop()
            if cert_path and os.path.exists(cert_path):
                os.remove(cert_path)
            if key_path and os.path.exists(key_path):
                os.remove(key_path)
            if os.path.exists(tmp_dir):
                import shutil
                shutil.rmtree(tmp_dir) # Remove a pasta temporária inteira
        except:
            pass
