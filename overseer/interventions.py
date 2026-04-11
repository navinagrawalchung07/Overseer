"""
overseer/interventions.py

Executes intervention strategies when a stuck agent is detected.
Each strategy is framework-agnostic — it writes to the agent's
intervention file, which the agent adapter picks up on next tick.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from overseer.config import AGENTS_DIR


def _agent_dir(agent_id: str) -> Path:
    d = AGENTS_DIR / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def inject_context(agent_id: str, message: str) -> dict:
    """
    Write a corrective message to the agent's intervention file.
    The agent's adapter reads this on next tick and injects it into context.
    """
    path = _agent_dir(agent_id) / "intervention.json"
    payload = {
        "type": "inject_context",
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consumed": False,
    }
    path.write_text(json.dumps(payload, indent=2))
    return {"strategy": "inject_context", "agent_id": agent_id, "ok": True}


def stop_and_restart(agent_id: str, revised_prompt: str) -> dict:
    """
    Signal the agent to stop and restart with a revised task prompt.
    In a real system this would SIGTERM the process; in demo mode it
    writes a restart signal file the simulator picks up.
    """
    path = _agent_dir(agent_id) / "intervention.json"
    payload = {
        "type": "stop_and_restart",
        "revised_prompt": revised_prompt,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consumed": False,
    }
    path.write_text(json.dumps(payload, indent=2))
    return {"strategy": "stop_and_restart", "agent_id": agent_id, "ok": True}


def escalate(agent_id: str, message: str, pattern: str) -> dict:
    """
    Flag for human review. In production this would fire a webhook,
    Slack notification, or PagerDuty alert.
    """
    path = _agent_dir(agent_id) / "escalation.json"
    payload = {
        "type": "escalate",
        "message": message,
        "pattern": pattern,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
    }
    path.write_text(json.dumps(payload, indent=2))
    return {"strategy": "escalate", "agent_id": agent_id, "ok": True}


def dispatch(agent_id: str, analysis: dict) -> dict:
    """
    Route to the right intervention strategy based on the analysis result.
    """
    strategy = analysis.get("intervention", "none")
    message  = analysis.get("message", "")
    pattern  = analysis.get("pattern", "")

    if strategy == "inject_context":
        return inject_context(agent_id, message)
    elif strategy == "stop_and_restart":
        return stop_and_restart(agent_id, message)
    elif strategy == "escalate":
        return escalate(agent_id, message, pattern)
    return {"strategy": "none", "agent_id": agent_id, "ok": True}
