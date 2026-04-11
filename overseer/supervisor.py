"""
overseer/supervisor.py

The main supervisor loop. Polls all registered agents, analyzes their
action windows, and dispatches interventions when loops are detected.

Can run as a background thread (for the dashboard) or as a standalone process.
"""
import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from overseer.config import (
    HOME_DIR, HISTORY_FILE, STATE_FILE,
    POLL_INTERVAL, MIN_ACTIONS, AGENTS_DIR
)
from overseer.adapters.file_watcher import (
    get_agent_ids, get_agent_meta, get_action_window, get_action_count
)
from overseer.agent import analyze_agent
from overseer.interventions import dispatch


# ── State ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"agents": {}, "total_interventions": 0, "total_tokens_saved": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def append_history(entry: dict) -> None:
    history = load_history()
    history.append(entry)
    history = history[-500:]  # cap at 500 events
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


# ── Core poll cycle ─────────────────────────────────────────────────────────

def poll_once(state: dict, on_event: Callable | None = None) -> dict:
    """
    Run one full poll cycle across all known agents.
    Updates state in place, fires on_event callbacks for the dashboard.
    Returns updated state.
    """
    agent_ids = get_agent_ids()

    for agent_id in agent_ids:
        meta    = get_agent_meta(agent_id)
        task    = meta.get("task", "Unknown task")
        actions = get_action_window(agent_id)
        count   = get_action_count(agent_id)

        # Init agent state entry
        if agent_id not in state["agents"]:
            state["agents"][agent_id] = {
                "agent_id":      agent_id,
                "task":          task,
                "status":        "healthy",
                "action_count":  0,
                "interventions": 0,
                "tokens_saved":  0,
                "last_analysis": None,
                "last_event":    None,
            }

        agent_state = state["agents"][agent_id]
        agent_state["action_count"] = count
        agent_state["task"] = task

        # Skip agents with too few actions
        if count < MIN_ACTIONS or len(actions) < MIN_ACTIONS:
            agent_state["status"] = "warming_up"
            _emit(on_event, "tick", agent_id, agent_state)
            continue

        # Check if agent has completed or been stopped
        if meta.get("status") == "completed":
            agent_state["status"] = "completed"
            _emit(on_event, "tick", agent_id, agent_state)
            continue

        # ── Call Perplexity Agent API ────────────────────────────────
        analysis = analyze_agent(agent_id, task, actions)
        now = datetime.now(timezone.utc).isoformat()

        agent_state["last_analysis"] = {
            "timestamp":  now,
            "status":     analysis["status"],
            "confidence": analysis["confidence"],
            "pattern":    analysis["pattern"],
        }

        if analysis["status"] != "healthy" and analysis["intervention"] != "none":
            # Dispatch intervention
            result = dispatch(agent_id, analysis)

            tokens_saved = analysis.get("tokens_wasted_estimate", 0)
            agent_state["status"]        = analysis["status"]
            agent_state["interventions"] += 1
            agent_state["tokens_saved"]  += tokens_saved
            agent_state["last_event"]    = {
                "type":        analysis["intervention"],
                "timestamp":   now,
                "pattern":     analysis["pattern"],
                "confidence":  analysis["confidence"],
                "message":     analysis["message"],
                "tokens_saved": tokens_saved,
            }

            state["total_interventions"] += 1
            state["total_tokens_saved"]  += tokens_saved

            history_entry = {
                "timestamp":    now,
                "agent_id":     agent_id,
                "task":         task[:80],
                "status":       analysis["status"],
                "intervention": analysis["intervention"],
                "pattern":      analysis["pattern"],
                "confidence":   analysis["confidence"],
                "tokens_saved": tokens_saved,
                "message":      analysis["message"][:120],
            }
            append_history(history_entry)
            _emit(on_event, "intervention", agent_id, agent_state, analysis)
        else:
            agent_state["status"] = "healthy"
            _emit(on_event, "tick", agent_id, agent_state)

    save_state(state)
    return state


def _emit(cb: Callable | None, event_type: str, agent_id: str, agent_state: dict, analysis: dict | None = None):
    if cb:
        try:
            cb(event_type, agent_id, agent_state, analysis)
        except Exception:
            pass


# ── Background runner ────────────────────────────────────────────────────────

class SupervisorThread(threading.Thread):
    """Run the supervisor in a background thread for the dashboard."""

    def __init__(self, on_event: Callable | None = None, interval: int = POLL_INTERVAL):
        super().__init__(daemon=True)
        self.on_event = on_event
        self.interval = interval
        self.state    = load_state()
        self._stop    = threading.Event()

    def run(self):
        while not self._stop.is_set():
            try:
                self.state = poll_once(self.state, self.on_event)
            except Exception:
                pass
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()

    def get_state(self) -> dict:
        return self.state
