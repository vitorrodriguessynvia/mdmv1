# =============================================================
#  main.py  —  Servidor MDM (FastAPI)
#  Fase 2: Backend que recebe checkins e gerencia comandos
# =============================================================

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import database as db

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield

app = FastAPI(title="MDM Server", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Em produção, troque pelo domínio do painel
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- AUTENTICAÇÃO ----
def get_device(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token inválido")
    token = authorization.replace("Bearer ", "")
    device = db.get_device_by_token(token)
    if not device:
        raise HTTPException(status_code=401, detail="Dispositivo não autorizado")
    return device

# ============================================================
#  ENROLLMENT
# ============================================================
from pydantic import BaseModel
from typing import Optional

class EnrollRequest(BaseModel):
    hostname: str
    os: str
    enrolled_at: str

@app.post("/api/enroll")
def enroll(req: EnrollRequest):
    device_id, token = db.create_device(req.hostname, req.os, req.enrolled_at)
    return {"device_id": device_id, "token": token}

# ============================================================
#  CHECKIN
# ============================================================
class CheckinRequest(BaseModel):
    inventory: dict
    checked_at: str

@app.post("/api/checkin")
def checkin(req: CheckinRequest, device=Depends(get_device)):
    db.save_inventory(device["id"], req.inventory, req.checked_at)
    db.update_device_status(device["id"], "online", req.checked_at)
    return {"status": "ok"}

# ============================================================
#  COMANDOS
# ============================================================
@app.get("/api/commands/pending")
def get_pending_commands(device=Depends(get_device)):
    commands = db.get_pending_commands(device["id"])
    return commands

class CommandResultRequest(BaseModel):
    command_id: int
    success: bool
    output: Optional[str] = ""
    error: Optional[str] = ""
    executed_at: str

@app.post("/api/commands/{command_id}/result")
def command_result(command_id: int, req: CommandResultRequest, device=Depends(get_device)):
    db.save_command_result(command_id, req.success, req.output, req.error, req.executed_at)
    return {"status": "ok"}

# ============================================================
#  PAINEL — endpoints usados pelo dashboard (Fase 3)
# ============================================================
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets, os

security = HTTPBasic()
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "troque-esta-senha")

def require_admin(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username, ADMIN_USER)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASS)
    if not (ok_user and ok_pass):
        raise HTTPException(status_code=401, detail="Credenciais inválidas",
                            headers={"WWW-Authenticate": "Basic"})
    return credentials.username

@app.get("/api/admin/devices")
def list_devices(admin=Depends(require_admin)):
    return db.list_devices()

@app.get("/api/admin/devices/{device_id}")
def get_device_detail(device_id: int, admin=Depends(require_admin)):
    device = db.get_device_detail(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo não encontrado")
    return device

@app.get("/api/admin/devices/{device_id}/inventory")
def get_inventory(device_id: int, admin=Depends(require_admin)):
    return db.get_latest_inventory(device_id)

@app.get("/api/admin/devices/{device_id}/commands")
def get_device_commands(device_id: int, admin=Depends(require_admin)):
    return db.get_device_commands(device_id)

class SendCommandRequest(BaseModel):
    type: str      # run_script | install_app | uninstall_app | apply_patches | reboot | get_inventory
    payload: Optional[str] = ""

@app.post("/api/admin/devices/{device_id}/commands")
def send_command(device_id: int, req: SendCommandRequest, admin=Depends(require_admin)):
    command_id = db.create_command(device_id, req.type, req.payload, admin)
    return {"command_id": command_id, "status": "queued"}

@app.post("/api/admin/devices/{device_id}/commands/bulk")
def send_bulk_command(device_id: int, req: SendCommandRequest, admin=Depends(require_admin)):
    """Envia um comando para múltiplos dispositivos de uma vez"""
    devices = db.list_devices()
    ids = [d["id"] for d in devices]
    created = []
    for did in ids:
        cid = db.create_command(did, req.type, req.payload, admin)
        created.append(cid)
    return {"commands_created": len(created)}

@app.delete("/api/admin/devices/{device_id}")
def remove_device(device_id: int, admin=Depends(require_admin)):
    db.delete_device(device_id)
    return {"status": "removed"}

@app.get("/api/admin/stats")
def get_stats(admin=Depends(require_admin)):
    return db.get_stats()
