# ============================================================
# [NOVO v2] app/robot/atende_scraper.py
#
# Integração via WebService SOAP IPM para consulta de NFS-e.
# Municípios suportados: São José/SC, Palhoça/SC, Biguaçu/SC
#
# MUDANÇA DE ESTRATÉGIA (01/05/2026):
#   Scraping com Playwright foi abandonado porque o portal Atende.Net
#   usa reCAPTCHA invisible validado pelo Google no servidor — tokens
#   gerados por browser headless são rejeitados pelo Google.
#
# NOVA ABORDAGEM: WebService SOAP IPM oficial
#   - Sem browser, sem captcha, sem Playwright
#   - Autenticação via username/password no header SOAP
#   - Endpoint: https://MUNICIPIO.atende.net/WsNFe2/LoteRps.jws
#   - Método: ConsultarNfse com filtro de período e CNPJ
#   - Pré-requisito: cliente deve ter WebService ativado no portal IPM
#     (Manutenção → Emissão de NFS-e por WebService → Liberar Acesso)
#
# Portais suportados:
#   São José/SC  → https://nfse-saojose.atende.net
#   Palhoça/SC   → https://nfse-palhoca.atende.net
#   Biguaçu/SC   → https://nfse-bigua.atende.net
#
# Ponto de entrada: importar_via_atende()
# Verificador:      is_portal_atende()
# ============================================================

import httpx
import xml.etree.ElementTree as ET
from datetime import datetime, date
import re


# ============================================================
# MAPEAMENTO DE PORTAIS → ENDPOINTS SOAP
# Chave  = fragmento do hostname (usado em portal_url)
# Valor  = configuração do endpoint WebService IPM
# ============================================================
PORTAIS_ATENDE = {
    "nfse-saojose.atende.net": {
        "nome":     "São José/SC",
        "base_url": "https://nfse-saojose.atende.net",
        # Endpoints IPM/Atende.Net — testados em ordem de prioridade
        "ws_urls": [
            "https://nfse-saojose.atende.net/WsNFe2/LoteRps.jws",
            "https://nfse-saojose.atende.net/nfse/services/NFSeServices",
            "https://nfse-saojose.atende.net/nfse/services/NFSeConsultas",
            "https://nfse-saojose.atende.net/WsNfe/NfseServices",
        ],
    },
    "nfse-palhoca.atende.net": {
        "nome":     "Palhoça/SC",
        "base_url": "https://nfse-palhoca.atende.net",
        "ws_urls": [
            "https://nfse-palhoca.atende.net/WsNFe2/LoteRps.jws",
            "https://nfse-palhoca.atende.net/nfse/services/NFSeServices",
            "https://nfse-palhoca.atende.net/nfse/services/NFSeConsultas",
            "https://nfse-palhoca.atende.net/WsNfe/NfseServices",
        ],
    },
    "nfse-bigua.atende.net": {
        "nome":     "Biguaçu/SC",
        "base_url": "https://nfse-bigua.atende.net",
        "ws_urls": [
            "https://nfse-bigua.atende.net/WsNFe2/LoteRps.jws",
            "https://nfse-bigua.atende.net/nfse/services/NFSeServices",
            "https://nfse-bigua.atende.net/nfse/services/NFSeConsultas",
            "https://nfse-bigua.atende.net/WsNfe/NfseServices",
        ],
    },
}


# ============================================================
# VERIFICADOR: IS_PORTAL_ATENDE
# ============================================================
def is_portal_atende(portal_url: str) -> bool:
    if not portal_url:
        return False
    return any(host in portal_url for host in PORTAIS_ATENDE)


def _get_portal_config(portal_url: str) -> dict | None:
    for host, config in PORTAIS_ATENDE.items():
        if host in portal_url:
            return config
    return None


# ============================================================
# HELPER: NORMALIZA DATA
# Aceita DD/MM/YYYY ou YYYY-MM-DD e retorna YYYY-MM-DD
# ============================================================
def _normalizar_data(d: str) -> str:
    if "/" in d and len(d) == 10:
        partes = d.split("/")
        return f"{partes[2]}-{partes[1]}-{partes[0]}"
    return d


# ============================================================
# HELPER: LIMPA CNPJ (remove pontos, barras, traços)
# ============================================================
def _limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"[^0-9]", "", cnpj)


# ============================================================
# MONTA ENVELOPE SOAP: ConsultarNfse
# Autentica via header SOAP com username e password.
# Filtra por CNPJ do prestador e período de competência.
# ============================================================
def _montar_soap_consultar_nfse(
    cnpj: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
) -> str:
    cnpj_limpo = _limpar_cnpj(cnpj)
    di = _normalizar_data(data_inicio)
    df = _normalizar_data(data_fim)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:nfse="http://nfse.abrasf.org.br/">
  <soapenv:Header>
    <nfse:cabecalho>
      <versaoDados>1.00</versaoDados>
    </nfse:cabecalho>
    <wsse:Security
        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{usuario}</wsse:Username>
        <wsse:Password>{senha}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <nfse:ConsultarNfseServicoPrestadoEnvio>
      <Prestador>
        <Cnpj>{cnpj_limpo}</Cnpj>
      </Prestador>
      <PeriodoEmissao>
        <DataInicial>{di}</DataInicial>
        <DataFinal>{df}</DataFinal>
      </PeriodoEmissao>
    </nfse:ConsultarNfseServicoPrestadoEnvio>
  </soapenv:Body>
</soapenv:Envelope>"""


# ============================================================
# MONTA ENVELOPE SOAP: ConsultarNfse (formato alternativo IPM)
# Alguns municípios IPM usam formato ligeiramente diferente
# ============================================================
def _montar_soap_ipm(
    cnpj: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
) -> str:
    cnpj_limpo = _limpar_cnpj(cnpj)
    di = _normalizar_data(data_inicio)
    df = _normalizar_data(data_fim)

    xml_consulta = f"""<ConsultarNfseServicoPrestadoEnvio xmlns="http://www.abrasf.org.br/nfse.xsd">
  <Prestador>
    <CpfCnpj>
      <Cnpj>{cnpj_limpo}</Cnpj>
    </CpfCnpj>
  </Prestador>
  <PeriodoEmissao>
    <DataInicial>{di}</DataInicial>
    <DataFinal>{df}</DataFinal>
  </PeriodoEmissao>
</ConsultarNfseServicoPrestadoEnvio>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ws="http://ws.issweb.fiorilli.com.br/">
  <soapenv:Header>
    <wsse:Security
        xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
      <wsse:UsernameToken>
        <wsse:Username>{usuario}</wsse:Username>
        <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordText">{senha}</wsse:Password>
      </wsse:UsernameToken>
    </wsse:Security>
  </soapenv:Header>
  <soapenv:Body>
    <ws:consultarNfseServicoPrestado>
      <xml>{xml_consulta}</xml>
      <username>{usuario}</username>
      <password>{senha}</password>
    </ws:consultarNfseServicoPrestado>
  </soapenv:Body>
</soapenv:Envelope>"""


# ============================================================
# PARSEIA RESPOSTA XML: extrai lista de notas
# ============================================================
def _parsear_notas_xml(xml_resposta: str) -> list:
    notas = []
    try:
        # Remove namespaces para facilitar parsing
        xml_limpo = re.sub(r' xmlns[^"]*"[^"]*"', '', xml_resposta)
        xml_limpo = re.sub(r'<[a-zA-Z]+:', '<', xml_limpo)
        xml_limpo = re.sub(r'</[a-zA-Z]+:', '</', xml_limpo)

        root = ET.fromstring(xml_limpo)

        # Busca todos os elementos CompNfse (nota completa)
        comp_nfses = root.findall('.//CompNfse') or root.findall('.//Nfse')

        for comp in comp_nfses:
            try:
                nota = {}

                # Número da nota
                num_el = comp.find('.//Numero') or comp.find('.//NumeroNfse')
                nota['numero_nota'] = num_el.text if num_el is not None else ''

                # Data de emissão
                data_el = comp.find('.//DataEmissao') or comp.find('.//DataCompetencia')
                nota['data_emissao'] = data_el.text if data_el is not None else ''

                # Valor do serviço
                valor_el = comp.find('.//ValorServicos') or comp.find('.//ValorLiquidoNfse')
                nota['valor_servico'] = valor_el.text if valor_el is not None else ''

                # Tomador
                tom_nome = comp.find('.//RazaoSocial') or comp.find('.//NomeTomador')
                nota['tomador'] = tom_nome.text if tom_nome is not None else ''

                # CNPJ tomador
                tom_cnpj = comp.find('.//Cnpj') or comp.find('.//CpfCnpj/Cnpj')
                nota['cnpj_tomador'] = tom_cnpj.text if tom_cnpj is not None else ''

                # Chave de acesso / código verificação
                chave_el = comp.find('.//CodigoVerificacao') or comp.find('.//ChaveAcesso')
                nota['chave_acesso'] = chave_el.text if chave_el is not None else nota['numero_nota']

                # Situação
                sit_el = comp.find('.//Situacao') or comp.find('.//Status')
                nota['situacao'] = sit_el.text if sit_el is not None else 'N'

                nota['origem'] = 'atende_net_soap'
                nota['url_download'] = None
                nota['url_danfse'] = None

                notas.append(nota)
            except Exception as e:
                print(f"⚠️  [Atende SOAP] Erro ao parsear nota: {e}")
                continue

        print(f"✅ [Atende SOAP] {len(notas)} nota(s) parseada(s) do XML")

    except ET.ParseError as e:
        print(f"❌ [Atende SOAP] Erro ao parsear XML: {e}")
        print(f"   XML recebido: {xml_resposta[:500]}")

    return notas


# ============================================================
# CHAMA O WEBSERVICE SOAP
# Tenta múltiplos formatos de envelope SOAP pois o IPM
# pode variar levemente entre municípios.
# ============================================================
async def _chamar_webservice(
    ws_url: str,
    soap_body: str,
    soap_action: str = "",
    timeout: int = 60,
) -> str | None:
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": soap_action,
    }

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            verify=False,  # alguns portais municipais têm cert auto-assinado
            follow_redirects=True,
        ) as client:
            print(f"📤 [Atende SOAP] POST → {ws_url}")
            resp = await client.post(ws_url, content=soap_body.encode("utf-8"), headers=headers)
            print(f"📥 [Atende SOAP] Status: {resp.status_code}")

            if resp.status_code == 200:
                return resp.text
            else:
                print(f"❌ [Atende SOAP] Erro HTTP {resp.status_code}: {resp.text[:300]}")
                return None

    except httpx.ConnectError as e:
        print(f"❌ [Atende SOAP] Conexão falhou: {e}")
        return None
    except httpx.TimeoutException:
        print(f"❌ [Atende SOAP] Timeout após {timeout}s")
        return None
    except Exception as e:
        print(f"❌ [Atende SOAP] Erro inesperado: {e}")
        return None


# ============================================================
# FUNÇÃO PRINCIPAL: IMPORTAR VIA ATENDE (WebService SOAP)
# Chamada pelo endpoint POST /importar-notas-municipal
# ============================================================
async def importar_via_atende(
    portal_url: str,
    usuario: str,
    senha: str,
    data_inicio: str,
    data_fim: str,
) -> dict:

    config = _get_portal_config(portal_url)
    if not config:
        raise Exception(f"Portal não suportado: {portal_url}")

    municipio = config["nome"]
    ws_url = config.get("ws_urls", [""])[0]  # URL principal (fallback)

    print(f"🏙️  [Atende SOAP] ══════════════════════════════")
    print(f"🏙️  [Atende SOAP] {municipio} | {data_inicio} → {data_fim}")
    print(f"   WebService: {ws_url}")
    print(f"   Usuário   : {usuario}")
    print(f"🏙️  [Atende SOAP] ══════════════════════════════")

    # Extrai CNPJ do usuário (campo portal_usuario é o CNPJ/CPF)
    cnpj = usuario

    notas = []
    xml_resposta = None
    ws_urls = config.get("ws_urls", [config.get("ws_url", "")])

    # ── Testa todos os endpoints em ordem ────────────────────
    for idx, ws_url_atual in enumerate(ws_urls):
        print(f"🔄 [Atende SOAP] Endpoint {idx+1}/{len(ws_urls)}: {ws_url_atual}")

        # Verifica se endpoint existe (GET)
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            try:
                r = await client.get(f"{ws_url_atual}?WSDL")
                print(f"   WSDL status: {r.status_code}")
                if r.status_code == 404:
                    print(f"   ❌ Endpoint 404 — pulando")
                    continue
                if r.status_code == 200:
                    print(f"   ✅ WSDL encontrado: {r.text[:200]}")
            except Exception as e:
                print(f"   ⚠️  Erro ao verificar WSDL: {e}")
                continue

        # Tentativa ABRASF padrão
        soap1 = _montar_soap_consultar_nfse(cnpj, usuario, senha, data_inicio, data_fim)
        resp = await _chamar_webservice(
            ws_url_atual, soap1,
            soap_action="http://nfse.abrasf.org.br/ConsultarNfseServicoPrestado"
        )
        if resp:
            print(f"   Resposta ABRASF: {resp[:300]}")
            notas_encontradas = _parsear_notas_xml(resp)
            if notas_encontradas:
                notas = notas_encontradas
                xml_resposta = resp
                print(f"✅ [Atende SOAP] ABRASF OK em {ws_url_atual} — {len(notas)} notas")
                break

        # Tentativa IPM alternativa
        soap2 = _montar_soap_ipm(cnpj, usuario, senha, data_inicio, data_fim)
        resp2 = await _chamar_webservice(
            ws_url_atual, soap2,
            soap_action="consultarNfseServicoPrestado"
        )
        if resp2:
            print(f"   Resposta IPM: {resp2[:300]}")
            notas_encontradas2 = _parsear_notas_xml(resp2)
            if notas_encontradas2:
                notas = notas_encontradas2
                xml_resposta = resp2
                print(f"✅ [Atende SOAP] IPM OK em {ws_url_atual} — {len(notas)} notas")
                break
            xml_resposta = resp2  # guarda mesmo sem notas para diagnóstico

    print(f"🏁 [Atende SOAP] Concluído — {len(notas)} nota(s) encontrada(s)")

    return {
        "status": "concluido",
        "municipio": municipio,
        "notas_encontradas": len(notas),
        "notas": notas,
        "xml_bruto": xml_resposta[:2000] if xml_resposta else None,
    }
