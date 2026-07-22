"""
FastAPI backend for the TeleFeed Web UI.

Serves REST endpoints + WebSocket for real-time match streaming,
and static frontend assets compiled by Vite.
"""

import asyncio
import logging
import platform
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from telefeed.config import (
    CONFIG_TEMPLATE,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_SESSION_FILE,
    DEFAULT_STATE_DIR,
    load_telefeed_config,
)
from telefeed.service import install_service, service_action, uninstall_service
from telefeed.store import get_matches, init_db, update_match_status

logger = logging.getLogger("telefeed.web")

app = FastAPI(title="TeleFeed Web UI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module-level state for the auth flow
_auth_client = None
_auth_phone = None


# ──────────────────────────────────────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup():
    """Ensure the database and its tables exist."""
    DEFAULT_STATE_DIR.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(init_db, str(DEFAULT_DB_PATH))


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    """Return the full config.yaml as JSON."""
    if not DEFAULT_CONFIG_PATH.exists():
        return {}
    with DEFAULT_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.post("/api/config")
async def save_config(config_data: dict[str, Any]):
    """Overwrite config.yaml with the provided JSON."""
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, sort_keys=False, default_flow_style=False)
    return {"status": "ok"}


@app.post("/api/config/init")
async def init_config():
    """Create a default config.yaml if one doesn't exist."""
    if DEFAULT_CONFIG_PATH.exists():
        return {"status": "exists", "message": "Config already exists."}
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_CONFIG_PATH.open("w", encoding="utf-8") as f:
        f.write(CONFIG_TEMPLATE)
    return {"status": "ok", "message": "Default config created."}


# ──────────────────────────────────────────────────────────────────────────────
# Telegram Auth
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/auth/status")
async def auth_status():
    """Check if a valid Telegram session exists."""
    try:
        from telethon import TelegramClient
        cfg = load_telefeed_config()
        if not cfg.telegram.api_id or not cfg.telegram.api_hash:
            return {"authenticated": False, "user": None, "error": "Telegram credentials not configured."}

        client = TelegramClient(
            str(cfg.session_path), cfg.telegram.api_id, cfg.telegram.api_hash
        )
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            await client.disconnect()
            return {
                "authenticated": True,
                "user": f"{me.first_name} (@{me.username})" if me.username else me.first_name,
            }
        await client.disconnect()
        return {"authenticated": False, "user": None}
    except Exception as e:
        return {"authenticated": False, "user": None, "error": str(e)}


@app.post("/api/auth/start")
async def auth_start():
    """Send a Telegram OTP code to the configured phone number."""
    global _auth_client, _auth_phone
    try:
        from telethon import TelegramClient
        cfg = load_telefeed_config()

        if not cfg.telegram.api_id or not cfg.telegram.api_hash or not cfg.telegram.phone:
            raise HTTPException(status_code=400, detail="Telegram credentials not configured. Save them in Settings first.")

        # Clean up any previous auth attempt
        if _auth_client is not None:
            try:
                await _auth_client.disconnect()
            except Exception:
                pass

        _auth_phone = cfg.telegram.phone
        _auth_client = TelegramClient(
            str(cfg.session_path), cfg.telegram.api_id, cfg.telegram.api_hash
        )
        await _auth_client.connect()

        if await _auth_client.is_user_authorized():
            me = await _auth_client.get_me()
            await _auth_client.disconnect()
            _auth_client = None
            return {"status": "already_authorized", "user": f"{me.first_name} (@{me.username})" if me.username else me.first_name}

        await _auth_client.send_code_request(_auth_phone)
        return {"status": "code_sent", "phone": _auth_phone}
    except HTTPException:
        raise
    except Exception as e:
        _auth_client = None
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/verify")
async def auth_verify(payload: dict[str, str]):
    """Verify the OTP code."""
    global _auth_client, _auth_phone
    if _auth_client is None:
        raise HTTPException(status_code=400, detail="No auth session in progress. Click 'Send Code' first.")

    code = payload.get("code", "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Code is required.")

    try:
        from telethon.errors import SessionPasswordNeededError
        await _auth_client.sign_in(_auth_phone, code)
        me = await _auth_client.get_me()
        await _auth_client.disconnect()
        _auth_client = None
        _auth_phone = None
        return {"status": "ok", "user": f"{me.first_name} (@{me.username})" if me.username else me.first_name}
    except SessionPasswordNeededError:
        return {"status": "2fa_required"}
    except Exception as e:
        # Don't kill the client on error so user can retry
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/2fa")
async def auth_2fa(payload: dict[str, str]):
    """Submit the 2FA password."""
    global _auth_client, _auth_phone
    if _auth_client is None:
        raise HTTPException(status_code=400, detail="No auth session in progress.")

    password = payload.get("password", "").strip()
    if not password:
        raise HTTPException(status_code=400, detail="Password is required.")

    try:
        await _auth_client.sign_in(password=password)
        me = await _auth_client.get_me()
        await _auth_client.disconnect()
        _auth_client = None
        _auth_phone = None
        return {"status": "ok", "user": f"{me.first_name} (@{me.username})" if me.username else me.first_name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics (doctor)
# ──────────────────────────────────────────────────────────────────────────────

def _run_doctor_sync() -> list[dict]:
    """Run diagnostics synchronously (called via to_thread)."""
    cfg = load_telefeed_config()
    checks = []

    checks.append({
        "label": "Config file",
        "value": str(cfg.config_path),
        "ok": cfg.config_path.exists(),
    })
    checks.append({
        "label": "Database",
        "value": str(cfg.db_path),
        "ok": cfg.db_path.exists(),
    })

    session_path = DEFAULT_SESSION_FILE
    session_exists = session_path.exists() or Path(str(session_path) + ".session").exists()
    checks.append({
        "label": "Telegram session",
        "value": str(session_path),
        "ok": session_exists,
    })

    has_tg = bool(cfg.telegram.api_id and cfg.telegram.api_hash and cfg.telegram.phone)
    placeholder = cfg.telegram.api_id == 12345678 or cfg.telegram.api_hash == "your_api_hash_here"
    checks.append({
        "label": "Telegram credentials",
        "value": "Present" if has_tg and not placeholder else "Missing or placeholder",
        "ok": has_tg and not placeholder,
    })

    checks.append({
        "label": "Matcher mode",
        "value": f"{cfg.matcher} (threshold: {cfg.ai_threshold})",
        "ok": True,
    })

    if cfg.matcher == "ai":
        if cfg.ai.provider == "ollama":
            checks.append({"label": "AI provider", "value": f"Ollama \u2014 {cfg.ai.model} (no key needed)", "ok": True})
        elif cfg.ai.api_key:
            checks.append({"label": "AI provider", "value": f"{cfg.ai.provider} \u2014 {cfg.ai.model}", "ok": True})
        else:
            checks.append({"label": "AI provider", "value": f"{cfg.ai.provider} \u2014 API key missing", "ok": False})

    checks.append({"label": "Desktop notifications", "value": "Enabled" if cfg.notifications.desktop else "Disabled", "ok": True})
    bot = cfg.notifications.telegram_bot
    if bot.enabled:
        bot_ok = bool(bot.bot_token and bot.chat_id)
        checks.append({"label": "Telegram Bot", "value": "Configured" if bot_ok else "Missing token or chat_id", "ok": bot_ok})
    else:
        checks.append({"label": "Telegram Bot", "value": "Disabled", "ok": True})

    checks.append({"label": "Areas of Concern", "value": f"{len(cfg.areas)} configured", "ok": len(cfg.areas) > 0})
    return checks


@app.get("/api/doctor")
async def doctor():
    """Return a diagnostic health report (runs in a thread to avoid blocking)."""
    checks = await asyncio.to_thread(_run_doctor_sync)
    return {"checks": checks}


# ──────────────────────────────────────────────────────────────────────────────
# Notifications Test
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/notifications/test")
async def test_notification():
    """Send a test notification via all enabled channels."""
    try:
        cfg = load_telefeed_config()
        from telefeed.notifications import NotificationManager
        notifier = NotificationManager(cfg.notifications)
        await notifier.notify_match(
            area_name="Test Area",
            channel_title="TeleFeed Web UI",
            text="This is a test notification from TeleFeed! If you see this, your notifications are working.",
            score=100,
            url="https://github.com",
            ai_reason="Test notification triggered from the web dashboard.",
        )
        return {"status": "ok", "message": "Test notification sent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Matches
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/matches")
async def list_matches(
    limit: int = 50,
    offset: int = 0,
    area: Optional[str] = None,
    status: Optional[str] = None,
):
    """Retrieve matches with optional filtering."""
    try:
        rows = await asyncio.to_thread(
            get_matches, str(DEFAULT_DB_PATH), area=area, status=status, limit=limit
        )
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/matches/{match_id}/status")
async def change_match_status(match_id: int, new_status: str = Query(...)):
    """Update a match's status (new, saved, archived)."""
    try:
        await asyncio.to_thread(update_match_status, str(DEFAULT_DB_PATH), match_id, new_status)
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Service Control
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/api/service/status")
async def get_service_status():
    """Check if the background service is currently running."""
    try:
        if platform.system().lower() == "windows":
            out = subprocess.check_output(
                'wmic process where "CommandLine like \'%telefeed fetch --live%\'" get ProcessId',
                shell=True, text=True,
            )
            running = any(line.strip().isdigit() for line in out.splitlines())
        else:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "telefeed.service"],
                capture_output=True, text=True,
            )
            running = result.stdout.strip() == "active"
        return {"running": running}
    except Exception:
        return {"running": False}


@app.post("/api/service/{action}")
async def control_service(action: str):
    """Run install, uninstall, start, stop, restart, or status."""
    try:
        if action == "install":
            await asyncio.to_thread(install_service)
        elif action == "uninstall":
            await asyncio.to_thread(uninstall_service)
        else:
            await asyncio.to_thread(service_action, action)
        return {"status": "ok", "action": action}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/service/logs")
async def get_service_logs():
    """Retrieve recent service logs."""
    try:
        if platform.system().lower() == "windows":
            log_file = DEFAULT_STATE_DIR / "telefeed.log"
            if not log_file.exists():
                return {"logs": ["Log file not found."]}
            out = subprocess.check_output(
                ["powershell", "-Command", f"Get-Content -Path '{log_file}' -Tail 200"],
                text=True,
            )
            return {"logs": out.splitlines()}
        else:
            out = subprocess.check_output(
                ["journalctl", "--user", "-u", "telefeed.service", "-n", "200", "--no-pager"],
                text=True,
            )
            return {"logs": out.splitlines()}
    except Exception as e:
        return {"logs": [f"Failed to fetch logs: {e}"]}


# ──────────────────────────────────────────────────────────────────────────────
# Manual Fetch
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/api/fetch")
async def manual_fetch(
    limit: int = 50,
    no_groups: bool = False,
    no_save: bool = False,
):
    """Trigger a manual backfill fetch in a background task."""
    try:
        from telefeed.client import TeleFeedClient
        from telefeed.engine import TeleFeedEngine
        from telefeed.filters import load_areas_from_config

        cfg = load_telefeed_config()

        client = TeleFeedClient(
            session_file=str(cfg.session_path),
            api_id=cfg.telegram.api_id,
            api_hash=cfg.telegram.api_hash,
            phone=cfg.telegram.phone,
        )

        areas = load_areas_from_config(cfg.areas)

        ai_scorer = None
        if cfg.matcher == "ai":
            try:
                from telefeed.ai_filter import build_scorer
                ai_scorer = build_scorer(cfg)
            except Exception as exc:
                logger.warning(f"Could not build AI scorer: {exc}")

        engine = TeleFeedEngine(
            client=client,
            config=cfg,
            areas=areas,
            ai_scorer=ai_scorer,
        )

        async def _run():
            try:
                await engine.run_fetch(limit, no_groups, no_save)
            except Exception as exc:
                logger.error(f"Background fetch failed: {exc}")
            finally:
                await client._client.disconnect()

        asyncio.create_task(_run())
        return {"status": "ok", "message": "Background fetch started."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# WebSocket Live Feed
# ──────────────────────────────────────────────────────────────────────────────

@app.websocket("/api/live")
async def websocket_live_feed(websocket: WebSocket):
    """Push new matches to connected clients in real-time via SQLite polling."""
    await websocket.accept()

    last_id = 0
    try:
        if DEFAULT_DB_PATH.exists():
            with sqlite3.connect(str(DEFAULT_DB_PATH)) as con:
                cur = con.execute("SELECT MAX(id) FROM matches")
                row = cur.fetchone()
                if row and row[0]:
                    last_id = row[0]

        while True:
            await asyncio.sleep(2)
            if not DEFAULT_DB_PATH.exists():
                continue

            with sqlite3.connect(str(DEFAULT_DB_PATH)) as con:
                con.row_factory = sqlite3.Row
                cur = con.execute(
                    "SELECT * FROM matches WHERE id > ? ORDER BY id ASC",
                    (last_id,),
                )
                new_matches = cur.fetchall()

                for match in new_matches:
                    last_id = max(last_id, match["id"])
                    await websocket.send_json(dict(match))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Static File Serving
# ──────────────────────────────────────────────────────────────────────────────

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    @app.get("/")
    async def index_fallback():
        return {"error": "UI not built. Run 'npm run build' inside the ui/ folder."}
