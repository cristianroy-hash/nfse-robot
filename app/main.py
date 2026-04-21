from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.routes.importar import router
# =========================
# ENDPOINT ROBO E-MAIL --> 20/04/2026
# =========================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
# =========================
# FIM --> 20/04/2026
# =========================

app = FastAPI(title="NFS-e Robot", version="1.0.0")


# =========================
# CORS (ajustado)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # depois você pode restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# ROTAS
# =========================
app.include_router(router)


# =========================
# STARTUP / SHUTDOWN
# =========================
@app.on_event("startup")
async def startup_event():
    print("🚀 API NFS-e Robot iniciada com sucesso")


@app.on_event("shutdown")
async def shutdown_event():
    print("🛑 API finalizando...")


# =========================
# HEALTH CHECK
# =========================
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "message": "NFS-e Robot online"
    }


# =========================
# ROOT (DEBUG)
# =========================
@app.get("/")
async def root():
    return {
        "message": "API NFS-e Robot funcionando",
        "docs": "/docs",
        "health": "/health"
    }
    

# =========================
# ENVIO EMAIL --> 20/04/2026
# =========================
@app.post("/enviar-email")
async def enviar_email(body: dict):
    try:
        destinatarios = body.get("destinatarios", [])
        assunto = body.get("assunto", "")
        html = body.get("html", "")

        remetente = os.environ.get("EMAIL_REMETENTE")
        senha = os.environ.get("EMAIL_SENHA_APP")

        if not remetente or not senha:
            return {"success": False, "error": "Credenciais de e-mail não configuradas"}

        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = f"NFS-e Manager <{remetente}>"
        msg["To"] = ", ".join(destinatarios)
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(remetente, senha)
            server.sendmail(remetente, destinatarios, msg.as_string())

        return {"success": True}

    except Exception as e:
        return {"success": False, "error": str(e)}
# =========================
# FIM --> 20/04/2026
# =========================

