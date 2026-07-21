import asyncio
import sqlite3
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import yaml

from telefeed.config import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH
from telefeed.service import service_action
from telefeed.store import get_matches

app = FastAPI(title="TeleFeed Web UI Backend")

# Allow CORS for the Vite dev server (usually localhost:5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
async def get_config() -> dict[str, Any]:
    if not DEFAULT_CONFIG_PATH.exists():
        return {}
    with DEFAULT_CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@app.post("/api/config")
async def save_config(config_data: dict[str, Any]):
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config_data, f, sort_keys=False)
    return {"status": "ok"}


@app.get("/api/matches")
async def list_matches(limit: int = 50):
    try:
        rows = get_matches(str(DEFAULT_DB_PATH), limit=limit)
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/service/{action}")
async def control_service(action: str):
    try:
        from telefeed.service import install_service, uninstall_service
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
    import platform
    import subprocess
    from telefeed.config import DEFAULT_STATE_DIR
    
    try:
        if platform.system().lower() == "windows":
            log_file = DEFAULT_STATE_DIR / "telefeed.log"
            if not log_file.exists():
                return {"logs": ["Log file not found."]}
            out = subprocess.check_output(["powershell", "-Command", f"Get-Content -Path '{log_file}' -Tail 100"], text=True)
            return {"logs": out.splitlines()}
        else:
            out = subprocess.check_output(["journalctl", "--user", "-u", "telefeed.service", "-n", "100", "--no-pager"], text=True)
            return {"logs": out.splitlines()}
    except Exception as e:
        return {"logs": [f"Failed to fetch logs: {e}"]}

@app.post("/api/fetch")
async def manual_fetch(limit: int = 50, no_groups: bool = False, no_save: bool = False):
    """Trigger a manual backfill fetch."""
    try:
        from telefeed.cli import load_telefeed_config
        from telefeed.engine import TeleFeedEngine
        from telefeed.client import TeleFeedClient
        
        cfg = load_telefeed_config()
        client = TeleFeedClient(cfg)
        engine = TeleFeedEngine(cfg, client)
        
        # We run it in a separate task so it doesn't block the API response
        asyncio.create_task(engine.run_fetch(limit, no_groups, no_save))
        return {"status": "ok", "message": "Background fetch started. Matches will appear in the live feed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/api/live")
async def websocket_live_feed(websocket: WebSocket):
    """
    Holds a websocket open with the UI and pushes new matches to it in real-time.
    We accomplish this by quickly polling the local SQLite database for new IDs.
    """
    await websocket.accept()
    
    last_id = 0
    try:
        # Find the highest ID currently in the DB so we only stream NEW matches
        if DEFAULT_DB_PATH.exists():
            with sqlite3.connect(DEFAULT_DB_PATH) as con:
                cur = con.execute("SELECT MAX(id) FROM matches")
                row = cur.fetchone()
                if row and row[0]:
                    last_id = row[0]
                
        while True:
            await asyncio.sleep(2)
            if not DEFAULT_DB_PATH.exists():
                continue
                
            with sqlite3.connect(DEFAULT_DB_PATH) as con:
                con.row_factory = sqlite3.Row
                cur = con.execute(
                    "SELECT * FROM matches WHERE id > ? ORDER BY id ASC", 
                    (last_id,)
                )
                new_matches = cur.fetchall()
                
                for match in new_matches:
                    last_id = max(last_id, match["id"])
                    await websocket.send_json(dict(match))
                    
    except WebSocketDisconnect:
        # Normal disconnection when user closes tab
        pass
    except Exception as e:
        print(f"WebSocket Error: {e}")

# Mount static files last so it doesn't override API routes
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    @app.get("/")
    async def index_fallback():
        return {"error": "UI not built. Please run 'npm run build' inside the ui/ folder."}
