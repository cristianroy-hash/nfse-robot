import httpx
import os
from datetime import datetime

ROBOT_URL = os.environ.get("ROBOT_URL", "http://localhost:8000")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

def get_clientes_ativos():
    """Busca todos os clientes com agendamento ativo no Supabase"""
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/import_schedules",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        },
        params={
            "active": "eq.true",
            "select": "*, clients(id, cnpj, name)"
        }
    )
    return response.json()

def get_credenciais(client_id: str):
    """Busca credenciais do cliente no Supabase"""
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_credentials",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}"
        },
        params={
            "client_id": f"eq.{client_id}",
            "select": "*"
        }
    )
    dados = response.json()
    return dados[0] if dados else None

def importar_cliente(cliente: dict, competencia: str):
    """Chama o robô para importar notas de um cliente"""
    client_id = cliente["clients"]["id"]
    cnpj = cliente["clients"]["cnpj"]
    nome = cliente["clients"]["name"]

    print(f"Importando cliente: {nome} — competência: {competencia}")

    credenciais = get_credenciais(client_id)
    if not credenciais:
        print(f"Sem credenciais para cliente {nome}")
        return

    payload = {
        "cliente_id": client_id,
        "cnpj": cnpj,
        "competencia": competencia
    }

    if credenciais["auth_type"] == "certificate":
        payload["certificado_base64"] = credenciais["certificate_path"]
        payload["certificado_senha"] = credenciais["certificate_password"]
    else:
        payload["portal_usuario"] = credenciais["portal_username"]
        payload["portal_senha"] = credenciais["portal_password"]

    response = httpx.post(
        f"{ROBOT_URL}/importar-notas",
        json=payload,
        timeout=300
    )

    print(f"Resultado {nome}: {response.json()}")

def main():
    # Pega competência do mês anterior
    hoje = datetime.now()
    if hoje.month == 1:
        competencia = f"{hoje.year - 1}-12"
    else:
        mes = str(hoje.month - 1).zfill(2)
        competencia = f"{hoje.year}-{mes}"

    print(f"Iniciando importação mensal — competência: {competencia}")

    clientes = get_clientes_ativos()
    print(f"Clientes com agendamento ativo: {len(clientes)}")

    for cliente in clientes:
        try:
            importar_cliente(cliente, competencia)
        except Exception as e:
            print(f"Erro no cliente {cliente}: {str(e)}")
            continue

    print("Importação mensal concluída!")

if __name__ == "__main__":
    main()
