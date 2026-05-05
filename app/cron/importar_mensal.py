import httpx
import os
import base64
import time
from datetime import datetime, timezone

# ─── Variáveis de ambiente (configurar no Railway) ───────────────────────────
ROBOT_URL    = os.environ.get("ROBOT_URL", "https://nfse-robot-production.up.railway.app")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── Supabase helpers ─────────────────────────────────────────────────────────

def supabase_get(path: str, params: dict = {}) -> list:
    r = httpx.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def supabase_post(path: str, body: dict) -> dict:
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, json=body)
    r.raise_for_status()
    return r.json()

def supabase_patch(path: str, params: dict, body: dict):
    r = httpx.patch(f"{SUPABASE_URL}/rest/v1/{path}", headers=HEADERS, params=params, json=body)
    r.raise_for_status()

# ─── Lógica principal ─────────────────────────────────────────────────────────

def get_agendamentos_do_dia(dia_hoje: int) -> list:
    """Busca agendamentos ativos configurados para hoje."""
    return supabase_get(
        "import_schedules",
        params={
            "active":        "eq.true",
            "dia_execucao":  f"eq.{dia_hoje}",
            "select":        "*, clients(id, name, cnpj)"
        }
    )

def ja_importou_competencia(client_id: str, data_inicio: str, data_fim: str) -> bool:
    """Verifica se a competência já foi importada com sucesso para este cliente."""
    resultado = supabase_get(
        "system_logs",
        params={
            "client_id":  f"eq.{client_id}",
            "action":     "eq.import",
            "status":     "in.(success,empty)",
            "data_inicio": f"eq.{data_inicio}",
            "data_fim":    f"eq.{data_fim}",
            "select":      "id",
            "limit":       "1"
        }
    )
    return len(resultado) > 0

def get_credenciais(client_id: str) -> dict | None:
    """Busca credenciais do cliente."""
    dados = supabase_get(
        "client_credentials",
        params={"client_id": f"eq.{client_id}", "select": "*"}
    )
    return dados[0] if dados else None

def get_certificado_base64(certificate_path: str) -> str | None:
    """
    Baixa o arquivo .pfx do Supabase Storage e converte para base64.
    O certificate_path é o caminho relativo no bucket 'certificates'.
    """
    try:
        url = f"{SUPABASE_URL}/storage/v1/object/certificates/{certificate_path}"
        r = httpx.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return base64.b64encode(r.content).decode("utf-8")
    except Exception as e:
        print(f"    ✗ Erro ao baixar certificado: {e}")
        return None

def calcular_competencia() -> tuple[str, str]:
    """
    Retorna data_inicio e data_fim da competência anterior (mês passado completo).
    """
    hoje = datetime.now(timezone.utc)
    if hoje.month == 1:
        ano, mes = hoje.year - 1, 12
    else:
        ano, mes = hoje.year, hoje.month - 1

    import calendar
    ultimo_dia = calendar.monthrange(ano, mes)[1]

    data_inicio = f"{ano}-{mes:02d}-01"
    data_fim    = f"{ano}-{mes:02d}-{ultimo_dia:02d}"
    return data_inicio, data_fim

def registrar_log(client_id: str, status: str, descricao: str,
                   data_inicio: str, data_fim: str, total_notas: int = 0):
    """Registra resultado da importação em system_logs."""
    try:
        supabase_post("system_logs", {
            "client_id":        client_id,
            "action":           "import",
            "description":      descricao,
            "status":           status,
            "data_inicio":      data_inicio,
            "data_fim":         data_fim,
            "total_notas":      total_notas,
            "executed_by_name": "Scheduler Automático"
        })
    except Exception as e:
        print(f"    ⚠ Erro ao registrar log: {e}")

def atualizar_agendamento(schedule_id: str, status: str, resultado: str):
    """Atualiza ultimo_executado e status no agendamento."""
    try:
        supabase_patch(
            "import_schedules",
            params={"id": f"eq.{schedule_id}"},
            body={
                "ultimo_executado": datetime.now(timezone.utc).isoformat(),
                "ultimo_status":    status,
                "ultimo_resultado": resultado,
                "updated_at":       datetime.now(timezone.utc).isoformat()
            }
        )
    except Exception as e:
        print(f"    ⚠ Erro ao atualizar agendamento: {e}")

def aguardar_conclusao(job_id: str, timeout_segundos: int = 300) -> dict:
    """Faz polling do status do job até completar ou timeout."""
    inicio = time.time()
    while time.time() - inicio < timeout_segundos:
        time.sleep(8)
        try:
            r = httpx.get(f"{ROBOT_URL}/status/{job_id}", timeout=30)
            data = r.json()
            status = data.get("status", "")
            print(f"    Status: {status}")
            if status in ("completed", "failed"):
                return data
        except Exception as e:
            print(f"    ⚠ Erro no polling: {e}")
    return {"status": "timeout", "notas": []}

def importar_cliente(agendamento: dict, data_inicio: str, data_fim: str):
    """Executa a importação de um cliente."""
    schedule_id = agendamento["id"]
    cliente     = agendamento.get("clients", {})
    client_id   = cliente.get("id")
    nome        = cliente.get("name", "Desconhecido")
    cnpj        = cliente.get("cnpj", "")

    print(f"\n  → Cliente: {nome} ({cnpj})")

    # ── 1. Verificar se já foi importado ─────────────────────────────────────
    if ja_importou_competencia(client_id, data_inicio, data_fim):
        print(f"    ✓ Competência {data_inicio}/{data_fim} já importada. Pulando.")
        atualizar_agendamento(schedule_id, "skipped", "Competência já importada anteriormente.")
        return

    # ── 2. Buscar credenciais ─────────────────────────────────────────────────
    creds = get_credenciais(client_id)
    if not creds:
        msg = "Sem credenciais cadastradas."
        print(f"    ✗ {msg}")
        registrar_log(client_id, "error", msg, data_inicio, data_fim)
        atualizar_agendamento(schedule_id, "error", msg)
        return

    # ── 3. Montar payload ─────────────────────────────────────────────────────
    # Gerar nome da pasta (igual à lógica do frontend)
    nome_normalizado = (
        nome.encode("ascii", "ignore").decode()
            .lower()
            .replace(" ", "_")
    )
    # Remover caracteres inválidos
    import re
    nome_pasta = re.sub(r"[^a-z0-9_]", "_", nome_normalizado)

    payload = {
        "cliente_id": nome_pasta,
        "cnpj":       cnpj,
        "data_inicio": data_inicio,
        "data_fim":    data_fim,
    }

    if creds["auth_type"] == "certificate":
        # ✅ CORREÇÃO: baixar o .pfx do Storage e converter para base64
        cert_b64 = get_certificado_base64(creds["certificate_path"])
        if not cert_b64:
            msg = "Não foi possível baixar o certificado do Storage."
            print(f"    ✗ {msg}")
            registrar_log(client_id, "error", msg, data_inicio, data_fim)
            atualizar_agendamento(schedule_id, "error", msg)
            return
        payload["certificado_base64"] = cert_b64
        payload["certificado_senha"]  = creds["certificate_password"]

    elif creds["auth_type"] == "user_password":
        payload["portal_usuario"] = creds.get("portal_username", "")
        payload["portal_senha"]   = creds.get("portal_password", "")

    # ── 4. Disparar importação ────────────────────────────────────────────────
    print(f"    Disparando importação...")
    try:
        r = httpx.post(f"{ROBOT_URL}/importar-notas", json=payload, timeout=60)
        data = r.json()
    except Exception as e:
        msg = f"Erro ao chamar o robô: {e}"
        print(f"    ✗ {msg}")
        registrar_log(client_id, "error", msg, data_inicio, data_fim)
        atualizar_agendamento(schedule_id, "error", msg)
        return

    job_id = data.get("job_id")
    if not job_id:
        msg = f"Robô não retornou job_id: {data.get('error', 'sem detalhe')}"
        print(f"    ✗ {msg}")
        registrar_log(client_id, "error", msg, data_inicio, data_fim)
        atualizar_agendamento(schedule_id, "error", msg)
        return

    print(f"    Job ID: {job_id}. Aguardando conclusão...")

    # ── 5. Aguardar conclusão via polling ─────────────────────────────────────
    resultado = aguardar_conclusao(job_id)
    status_job = resultado.get("status")
    notas      = resultado.get("notas", [])

    if status_job == "completed":
        total = len(notas)
        if total == 0:
            msg = "Consulta realizada — nenhuma nota encontrada no período."
            registrar_log(client_id, "empty", msg, data_inicio, data_fim, 0)
            atualizar_agendamento(schedule_id, "empty", msg)
            print(f"    📭 {msg}")
        else:
            msg = f"{total} notas importadas automaticamente."
            registrar_log(client_id, "success", msg, data_inicio, data_fim, total)
            atualizar_agendamento(schedule_id, "success", msg)
            print(f"    ✓ {msg}")

    elif status_job == "failed":
        msg = f"Robô retornou falha: {resultado.get('error', 'sem detalhe')}"
        registrar_log(client_id, "error", msg, data_inicio, data_fim)
        atualizar_agendamento(schedule_id, "error", msg)
        print(f"    ✗ {msg}")

    elif status_job == "timeout":
        msg = "Timeout aguardando o robô (5 min). Verificar manualmente."
        registrar_log(client_id, "error", msg, data_inicio, data_fim)
        atualizar_agendamento(schedule_id, "error", msg)
        print(f"    ⚠ {msg}")

    # Pausa entre clientes para não sobrecarregar o robô
    time.sleep(5)

# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    agora     = datetime.now(timezone.utc)
    dia_hoje  = agora.day
    data_inicio, data_fim = calcular_competencia()

    print(f"{'='*60}")
    print(f"Scheduler NFS-e — {agora.strftime('%d/%m/%Y %H:%M UTC')}")
    print(f"Competência: {data_inicio} → {data_fim}")
    print(f"Dia de execução configurado: {dia_hoje}")
    print(f"{'='*60}")

    agendamentos = get_agendamentos_do_dia(dia_hoje)
    print(f"Agendamentos ativos para hoje: {len(agendamentos)}")

    if not agendamentos:
        print("Nenhum agendamento para executar hoje.")
        return

    for agendamento in agendamentos:
        try:
            importar_cliente(agendamento, data_inicio, data_fim)
        except Exception as e:
            nome = agendamento.get("clients", {}).get("name", "?")
            print(f"  ✗ Erro inesperado em {nome}: {e}")
            continue

    print(f"\n{'='*60}")
    print("Scheduler concluído.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
