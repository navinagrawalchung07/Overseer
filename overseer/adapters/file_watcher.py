"""
overseer/adapters/file_watcher.py

Level 1 adapter: watches a directory of agent log files.
Each agent writes a JSON-lines file:
  ~/.overseer/agents/<agent_id>/actions.jsonl

The supervisor reads these files to get action windows.
This requires zero changes to the watched agent's code.
"""
import json
from pathlib import Path
from overseer.config import AGENTS_DIR, WINDOW_SIZE


def get_agent_ids() -> list[str]:
    """Return all agent IDs found in the agents directory."""
    if not AGENTS_DIR.exists():
        return []
    return [d.name for d in AGENTS_DIR.iterdir() if d.is_dir()]


def get_agent_meta(agent_id: str) -> dict:
    """Load agent metadata (task description, start time, status)."""
    path = AGENTS_DIR / agent_id / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {"agent_id": agent_id, "task": "Unknown task", "status": "unknown"}


def get_action_window(agent_id: str, n: int = WINDOW_SIZE) -> list[dict]:
    """Return the last N actions from an agent's action log."""
    path = AGENTS_DIR / agent_id / "actions.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text().strip().splitlines()
        actions = []
        for line in lines:
            try:
                actions.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return actions[-n:]
    except OSError:
        return []


def get_action_count(agent_id: str) -> int:
    """Return total number of actions logged."""
    path = AGENTS_DIR / agent_id / "actions.jsonl"
    if not path.exists():
        return 0
    try:
        return len(path.read_text().strip().splitlines())
    except OSError:
        return 0


def check_intervention(agent_id: str) -> dict | None:
    """Check if there's a pending intervention for this agent."""
    path = AGENTS_DIR / agent_id / "intervention.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not data.get("consumed"):
            return data
    except Exception:
        pass
    return None


def mark_intervention_consumed(agent_id: str) -> None:
    """Mark an intervention as consumed by the agent."""
    path = AGENTS_DIR / agent_id / "intervention.json"
    if path.exists():
        try:
            data = json.loads(path.read_text())
            data["consumed"] = True
            path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
