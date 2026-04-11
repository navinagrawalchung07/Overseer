"""
overseer/server.py

FastAPI backend that:
- Serves the current supervisor state as JSON
- Streams real-time events to the dashboard via SSE
- Exposes API for the dashboard to trigger manual interventions
"""
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from overseer.supervisor import SupervisorThread, load_history
from overseer.config import POLL_INTERVAL, DASHBOARD_PORT

app = FastAPI(title="Overseer API")

# Serve the dashboard static files
DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR)), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Event queue for SSE ──────────────────────────────────────────────────────
_event_queue: asyncio.Queue = None
_supervisor: SupervisorThread = None


def _on_supervisor_event(event_type: str, agent_id: str, agent_state: dict, analysis: dict | None):
    """Called by supervisor thread when something happens."""
    global _event_queue
    if _event_queue is None:
        return
    event = {
        "type":        event_type,
        "agent_id":    agent_id,
        "agent_state": agent_state,
        "analysis":    analysis,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }
    try:
        _event_queue.put_nowait(event)
    except Exception:
        pass


@app.on_event("startup")
async def startup():
    global _event_queue, _supervisor
    _event_queue = asyncio.Queue()
    _supervisor  = SupervisorThread(on_event=_on_supervisor_event, interval=POLL_INTERVAL)
    _supervisor.start()


@app.on_event("shutdown")
async def shutdown():
    if _supervisor:
        _supervisor.stop()


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/")
def serve_dashboard():
    index = DASHBOARD_DIR / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"error": "dashboard not found"}, status_code=404)


# ── REST endpoints ───────────────────────────────────────────────────────────

@app.get("/api/state")
def get_state():
    if _supervisor is None:
        return JSONResponse({"agents": {}, "total_interventions": 0, "total_tokens_saved": 0})
    return JSONResponse(_supervisor.get_state())


@app.get("/api/history")
def get_history(limit: int = 50):
    history = load_history()
    return JSONResponse({"history": history[-limit:]})


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str):
    if _supervisor is None:
        return JSONResponse({}, status_code=404)
    state = _supervisor.get_state()
    agent = state.get("agents", {}).get(agent_id)
    if not agent:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(agent)


# ── SSE stream ───────────────────────────────────────────────────────────────

@app.get("/api/events")
async def event_stream():
    async def generator():
        global _event_queue
        while True:
            try:
                event = await asyncio.wait_for(_event_queue.get(), timeout=5.0)
                yield f"data: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': datetime.now(timezone.utc).isoformat()})}\n\n"
            except Exception:
                break

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
