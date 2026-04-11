"""
overseer/adapters/sdk.py

Level 2 adapter: instruments any agent function with Overseer tracking.

There are two ways to use this:

────────────────────────────────────────────────────────────────────────────
Option A — @tracked decorator (generic / custom agents)
────────────────────────────────────────────────────────────────────────────
Use this when your agent is a plain Python function or class and you want
to manually log actions and poll for interventions.

    from overseer.adapters.sdk import tracked, log_action

    @tracked(agent_id="my-agent", task="Fix the auth bug")
    def run():
        while True:
            # Do agent work...
            log_action("my-agent", "Read", "src/auth/token.ts", tokens=1240)

            # Check if Overseer has sent a corrective message
            iv = run.check_intervention()
            if iv:
                if iv["type"] == "inject_context":
                    # Re-orient the agent with the corrective message
                    context = iv["message"]
                    # ... pass context to your LLM call
                elif iv["type"] == "stop_and_restart":
                    # Restart with the revised prompt
                    new_prompt = iv["revised_prompt"]
                    break

────────────────────────────────────────────────────────────────────────────
Option B — CrewAI native integration (recommended for CrewAI users)
────────────────────────────────────────────────────────────────────────────
Replace Crew(...) with overseer_crew(...). Zero other changes required.

    from overseer.adapters.crewai_adapter import overseer_crew

    crew = overseer_crew(
        agent_id="bug-fixer",
        task="Fix the token expiry bug in src/auth/",
        agents=[researcher, engineer],
        tasks=[research_task, fix_task],
        process=Process.sequential,
    )
    crew.kickoff()

    See examples/crewai/bug_fixer_crew.py for a full working example.

────────────────────────────────────────────────────────────────────────────
"""
import json
import functools
from datetime import datetime, timezone
from pathlib import Path
from overseer.config import AGENTS_DIR


# ── Core: log_action ──────────────────────────────────────────────────────────

def log_action(agent_id: str, tool: str, key: str, tokens: int = 400) -> None:
    """
    Log a single agent action to Overseer's action buffer.

    Call this once per tool invocation from inside your agent loop.
    Overseer's supervisor reads these logs every poll interval and
    analyzes them for loop/drift/stall patterns.

    Args:
        agent_id: the agent's unique identifier (must match the one
                  passed to @tracked or overseer_crew)
        tool:     tool name, e.g. "Read", "Bash", "WebSearch"
        key:      a short descriptor of what was done, e.g. "src/auth/token.ts"
                  or "grep -r 'tokenExpiry' src/". Used for pattern matching.
        tokens:   estimated token cost of this action (used for savings calc)
    """
    path = AGENTS_DIR / agent_id / "actions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    action = {
        "tool":      tool,
        "key":       key,
        "tokens":    tokens,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with open(path, "a") as f:
        f.write(json.dumps(action) + "\n")


# ── @tracked decorator ────────────────────────────────────────────────────────

def tracked(agent_id: str, task: str):
    """
    Decorator that registers an agent function with Overseer.

    Attaches two helpers to the wrapped function:
      fn.log_action(tool, key, tokens)  — log one action
      fn.check_intervention()           — poll for pending intervention

    Example:
        @tracked(agent_id="auth-fixer", task="Fix token expiry bug in src/auth/")
        def run():
            files_seen = set()
            while True:
                for filepath in ["src/auth/token.ts", "src/auth/refresh.ts"]:
                    run.log_action("Read", filepath, tokens=1200)
                    files_seen.add(filepath)

                    # Check if Overseer wants us to change course
                    iv = run.check_intervention()
                    if iv:
                        if iv["type"] == "inject_context":
                            print(f"Overseer says: {iv['message']}")
                            # Inject the message as context on next LLM call
                        elif iv["type"] == "stop_and_restart":
                            print("Restarting with revised prompt...")
                            return  # caller should re-invoke with new prompt
                        break

        run()
    """
    def decorator(fn):
        _init_agent(agent_id, task)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        wrapper.log_action        = lambda tool, key, tokens=400: log_action(agent_id, tool, key, tokens)
        wrapper.check_intervention = lambda: _check_intervention(agent_id)
        return wrapper
    return decorator


# ── Internals ─────────────────────────────────────────────────────────────────

def _init_agent(agent_id: str, task: str) -> None:
    """Register a new agent with Overseer (creates meta.json)."""
    d = AGENTS_DIR / agent_id
    d.mkdir(parents=True, exist_ok=True)
    # Clear stale actions from a previous run
    actions_path = d / "actions.jsonl"
    if actions_path.exists():
        actions_path.unlink()
    meta = {
        "agent_id":   agent_id,
        "task":       task,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status":     "running",
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))


def _check_intervention(agent_id: str) -> dict | None:
    """
    Poll for a pending Overseer intervention for this agent.

    Returns the intervention dict if one is waiting, else None.
    Marks it consumed so it's only returned once.

    Intervention dict shape:
        {
            "type": "inject_context" | "stop_and_restart" | "escalate",
            "message": "...",          # for inject_context
            "revised_prompt": "...",   # for stop_and_restart
            "timestamp": "...",
            "consumed": True,
        }
    """
    from overseer.adapters.file_watcher import check_intervention, mark_intervention_consumed
    iv = check_intervention(agent_id)
    if iv:
        mark_intervention_consumed(agent_id)
        return iv
    return None


# ── Re-exports for convenience ────────────────────────────────────────────────
# Users can do: from overseer.adapters.sdk import overseer_crew
# instead of importing from the crewai_adapter directly.
try:
    from overseer.adapters.crewai_adapter import overseer_crew, OverseerStepCallback, OverseerTaskCallback
except ImportError:
    pass  # crewai not installed — fine, sdk still works without it
