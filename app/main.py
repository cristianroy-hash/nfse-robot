from fastapi import FastAPI

app = FastAPI(title="NFS-e Robot")

@app.get("/health")
def health():
    return {"status": "ok", "message": "NFS-e Robot online"}
