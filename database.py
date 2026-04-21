# =============================================================
#  database.py  —  Camada de banco de dados (SQLite)
#  Sem ORM — SQL puro para facilitar entendimento
# =============================================================

import sqlite3
import secrets
import json
import os
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "mdm.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # retorna dicts em vez de tuplas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

# ============================================================
#  CRIAÇÃO DAS TABELAS
# ============================================================
def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname     TEXT    NOT NULL,
            os           TEXT,
            token        TEXT    UNIQUE NOT NULL,
            status       TEXT    DEFAULT 'offline',
            enrolled_at  TEXT,
            last_seen    TEXT,
            created_at   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS inventories (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id    INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            data         TEXT    NOT NULL,   -- JSON completo do inventário
            collected_at TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS commands (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id    INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            type         TEXT    NOT NULL,
            payload      TEXT    DEFAULT '',
            status       TEXT    DEFAULT 'pending',  -- pending | running | done | failed
            created_by   TEXT    DEFAULT 'admin',
            output       TEXT    DEFAULT '',
            error        TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT (datetime('now')),
            executed_at  TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_commands_device_status
            ON commands(device_id, status);
        CREATE INDEX IF NOT EXISTS idx_inventories_device
            ON inventories(device_id);
        """)
    print(f"[DB] Banco inicializado em {DB_PATH}")

# ============================================================
#  DEVICES
# ============================================================
def create_device(hostname: str, os_name: str, enrolled_at: str):
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO devices (hostname, os, token, status, enrolled_at) VALUES (?,?,?,'online',?)",
            (hostname, os_name, token, enrolled_at)
        )
        return cur.lastrowid, token

def get_device_by_token(token: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM devices WHERE token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None

def update_device_status(device_id: int, status: str, last_seen: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE devices SET status=?, last_seen=? WHERE id=?",
            (status, last_seen, device_id)
        )

def list_devices():
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT d.id, d.hostname, d.os, d.status, d.last_seen, d.enrolled_at,
                   (SELECT COUNT(*) FROM commands WHERE device_id=d.id AND status='pending') AS pending_commands,
                   (SELECT COUNT(*) FROM commands WHERE device_id=d.id) AS total_commands
            FROM devices d
            ORDER BY d.hostname
        """).fetchall()
        return [dict(r) for r in rows]

def get_device_detail(device_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, hostname, os, status, last_seen, enrolled_at FROM devices WHERE id=?",
            (device_id,)
        ).fetchone()
        if not row:
            return None
        device = dict(row)
        # Inclui último inventário resumido
        inv = get_latest_inventory(device_id)
        if inv:
            device["os_version"]     = inv.get("os_version")
            device["os_build"]       = inv.get("os_build")
            device["ram_gb"]         = inv.get("ram_gb")
            device["cpu_name"]       = inv.get("cpu_name")
            device["ip_address"]     = inv.get("ip_address")
            device["pending_patches"] = len(inv.get("pending_updates", []))
            device["software_count"] = len(inv.get("software", []))
        return device

def delete_device(device_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))

# ============================================================
#  INVENTÁRIO
# ============================================================
def save_inventory(device_id: int, inventory: dict, collected_at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO inventories (device_id, data, collected_at) VALUES (?,?,?)",
            (device_id, json.dumps(inventory), collected_at)
        )
        # Mantém apenas os últimos 10 inventários por dispositivo
        conn.execute("""
            DELETE FROM inventories WHERE id NOT IN (
                SELECT id FROM inventories WHERE device_id=?
                ORDER BY created_at DESC LIMIT 10
            ) AND device_id=?
        """, (device_id, device_id))

def get_latest_inventory(device_id: int):
    with get_conn() as conn:
        row = conn.execute("""
            SELECT data, collected_at FROM inventories
            WHERE device_id=? ORDER BY created_at DESC LIMIT 1
        """, (device_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        data["collected_at"] = row["collected_at"]
        return data

# ============================================================
#  COMANDOS
# ============================================================
def get_pending_commands(device_id: int):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, type, payload FROM commands
            WHERE device_id=? AND status='pending'
            ORDER BY created_at ASC
        """, (device_id,)).fetchall()
        # Marca como 'running' para evitar execução dupla
        if rows:
            ids = tuple(r["id"] for r in rows)
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE commands SET status='running' WHERE id IN ({placeholders})", ids
            )
        return [dict(r) for r in rows]

def create_command(device_id: int, cmd_type: str, payload: str, created_by: str):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO commands (device_id, type, payload, created_by) VALUES (?,?,?,?)",
            (device_id, cmd_type, payload or "", created_by)
        )
        return cur.lastrowid

def save_command_result(command_id: int, success: bool, output: str, error: str, executed_at: str):
    status = "done" if success else "failed"
    with get_conn() as conn:
        conn.execute("""
            UPDATE commands SET status=?, output=?, error=?, executed_at=?
            WHERE id=?
        """, (status, output or "", error or "", executed_at, command_id))

def get_device_commands(device_id: int, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT id, type, payload, status, output, error, created_by, created_at, executed_at
            FROM commands WHERE device_id=?
            ORDER BY created_at DESC LIMIT ?
        """, (device_id, limit)).fetchall()
        return [dict(r) for r in rows]

# ============================================================
#  ESTATÍSTICAS (dashboard)
# ============================================================
def get_stats():
    with get_conn() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
        online    = conn.execute("SELECT COUNT(*) FROM devices WHERE status='online'").fetchone()[0]
        offline   = total - online
        pending   = conn.execute("SELECT COUNT(*) FROM commands WHERE status='pending'").fetchone()[0]
        failed    = conn.execute("SELECT COUNT(*) FROM commands WHERE status='failed'").fetchone()[0]

        # Patches pendentes totais (soma dos pending_updates de cada inventário mais recente)
        rows = conn.execute("""
            SELECT i.data FROM inventories i
            INNER JOIN (
                SELECT device_id, MAX(created_at) as max_at FROM inventories GROUP BY device_id
            ) latest ON i.device_id=latest.device_id AND i.created_at=latest.max_at
        """).fetchall()

        total_patches = 0
        for row in rows:
            try:
                inv = json.loads(row["data"])
                total_patches += len(inv.get("pending_updates", []))
            except Exception:
                pass

        return {
            "devices_total":   total,
            "devices_online":  online,
            "devices_offline": offline,
            "commands_pending": pending,
            "commands_failed":  failed,
            "patches_pending":  total_patches,
        }
