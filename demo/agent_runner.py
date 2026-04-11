"""
demo/agent_runner.py

Runs 3 simulated agents simultaneously. Each writes action logs that the
Overseer supervisor watches in real-time.

Agent A (auth-fixer):    LOOPING — reads token.ts repeatedly, gets stuck
Agent B (test-writer):   PROGRESSING — steadily writes new test files
Agent C (doc-updater):   COMPLETED — finishes quickly and exits

Run this alongside `overseer watch` or `overseer dashboard`.
"""
import json
import time
import threading
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from overseer.config import AGENTS_DIR
from overseer.adapters.sdk import log_action


def _init_agent(agent_id: str, task: str, status: str = "running"):
    d = AGENTS_DIR / agent_id
    d.mkdir(parents=True, exist_ok=True)
    # Clear old actions
    actions_path = d / "actions.jsonl"
    if actions_path.exists():
        actions_path.unlink()
    meta = {
        "agent_id":   agent_id,
        "task":       task,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status":     status,
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))


def _set_status(agent_id: str, status: str):
    meta_path = AGENTS_DIR / agent_id / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta["status"] = status
        meta_path.write_text(json.dumps(meta, indent=2))


def _check_intervention(agent_id: str) -> dict | None:
    path = AGENTS_DIR / agent_id / "intervention.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not data.get("consumed"):
            data["consumed"] = True
            path.write_text(json.dumps(data, indent=2))
            return data
    except Exception:
        pass
    return None


# ── Agent A: Auth Fixer (LOOPS) ───────────────────────────────────────────────
def run_agent_a():
    agent_id = "auth-fixer"
    task = "Fix token expiry bug in src/auth/token.ts"
    _init_agent(agent_id, task)
    print(f"[{agent_id}] Starting: {task}")

    # Phase 1: Healthy exploration
    actions_phase1 = [
        ("Read",    "src/auth/token.ts",              1240),
        ("Bash",    "grep -r 'tokenExpiry' src/",     680),
        ("Read",    "src/auth/refresh.ts",             980),
        ("Bash",    "grep -r 'refreshToken' src/",     720),
        ("Read",    "src/middleware/auth.ts",           860),
    ]
    for tool, key, tokens in actions_phase1:
        log_action(agent_id, tool, key, tokens)
        print(f"  [{agent_id}] {tool}: {key}")
        time.sleep(1.5)

    # Phase 2: Start looping
    loop_actions = [
        ("Read",    "src/auth/token.ts",              1240),
        ("Bash",    "grep -r 'tokenExpiry' src/",      680),
        ("Read",    "src/auth/token.ts",              1240),
        ("Read",    "src/auth/refresh.ts",             980),
        ("Bash",    "grep -r 'tokenExpiry' src/",      680),
        ("Read",    "src/auth/token.ts",              1240),
        ("Bash",    "grep -r 'refreshToken' src/",     720),
        ("Read",    "src/auth/token.ts",              1240),
        ("Bash",    "grep -r 'tokenExpiry' src/",      680),
        ("Read",    "src/auth/refresh.ts",             980),
    ]

    for tool, key, tokens in loop_actions:
        # Check for Overseer intervention before each action
        iv = _check_intervention(agent_id)
        if iv:
            itype = iv.get("type", "?")
            msg   = iv.get("message") or iv.get("revised_prompt", "")
            print(f"\n  [{agent_id}] 🛑 OVERSEER INTERVENED ({itype})")
            print(f"  [{agent_id}]    → {msg[:120]}")
            if itype == "stop_and_restart":
                print(f"  [{agent_id}] Restarting with revised prompt...")
                _set_status(agent_id, "restarting")
                time.sleep(2)
                # Simulate recovery: write the fix
                log_action(agent_id, "Edit", "src/auth/token.ts — update refreshBuffer to 300s", 400)
                log_action(agent_id, "Bash", "npm test src/auth/", 600)
                print(f"  [{agent_id}] Fixed! Tests passing.")
                _set_status(agent_id, "completed")
                return
            else:
                # inject_context: continue but with new direction
                log_action(agent_id, "Edit", "src/auth/token.ts — update refreshBuffer to 300s", 400)
                print(f"  [{agent_id}] Applied fix based on Overseer guidance.")
                _set_status(agent_id, "completed")
                return

        log_action(agent_id, tool, key, tokens)
        print(f"  [{agent_id}] {tool}: {key}  ← loop")
        time.sleep(1.2)

    _set_status(agent_id, "completed")


# ── Agent B: Test Writer (PROGRESSING) ──────────────────────────────────────
def run_agent_b():
    agent_id = "test-writer"
    task = "Write integration tests for the auth module"
    _init_agent(agent_id, task)
    print(f"[{agent_id}] Starting: {task}")

    steps = [
        ("Read",  "src/auth/token.ts",                        980),
        ("Read",  "src/auth/refresh.ts",                      760),
        ("Write", "tests/auth/token.test.ts — scaffold",      400),
        ("Bash",  "npx jest tests/auth/token.test.ts",        820),
        ("Edit",  "tests/auth/token.test.ts — add expiry case", 350),
        ("Bash",  "npx jest tests/auth/token.test.ts",        820),
        ("Write", "tests/auth/refresh.test.ts — scaffold",    400),
        ("Edit",  "tests/auth/refresh.test.ts — add cases",   350),
        ("Bash",  "npx jest tests/auth/",                     900),
        ("Write", "tests/auth/middleware.test.ts",            400),
        ("Bash",  "npx jest tests/auth/ --coverage",          950),
    ]

    for tool, key, tokens in steps:
        log_action(agent_id, tool, key, tokens)
        print(f"  [{agent_id}] {tool}: {key}")
        time.sleep(2.0)

    _set_status(agent_id, "completed")
    print(f"  [{agent_id}] Done — all tests written and passing.")


# ── Agent C: Doc Updater (COMPLETES FAST) ────────────────────────────────────
def run_agent_c():
    agent_id = "doc-updater"
    task = "Update API documentation for auth endpoints"
    _init_agent(agent_id, task)
    print(f"[{agent_id}] Starting: {task}")

    steps = [
        ("Read",  "docs/api/auth.md",              640),
        ("Read",  "src/auth/token.ts",             980),
        ("Write", "docs/api/auth.md — updated",    300),
        ("Write", "docs/api/refresh.md — new",     300),
        ("Bash",  "markdownlint docs/",            420),
    ]

    for tool, key, tokens in steps:
        log_action(agent_id, tool, key, tokens)
        print(f"  [{agent_id}] {tool}: {key}")
        time.sleep(1.0)

    _set_status(agent_id, "completed")
    print(f"  [{agent_id}] Done — docs updated.")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n👁  OVERSEER DEMO — Starting 3 simulated agents\n")
    print("=" * 65)
    print("  Agent A (auth-fixer):  will LOOP — Overseer should intervene")
    print("  Agent B (test-writer): making steady progress")
    print("  Agent C (doc-updater): completes quickly")
    print("=" * 65)
    print()
    print("Make sure `overseer watch` or `overseer dashboard` is running.\n")

    threads = [
        threading.Thread(target=run_agent_a, daemon=True),
        threading.Thread(target=run_agent_b, daemon=True),
        threading.Thread(target=run_agent_c, daemon=True),
    ]

    for t in threads:
        t.start()
        time.sleep(0.5)

    for t in threads:
        t.join()

    print("\n✅  All agents finished.")
