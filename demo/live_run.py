"""
live_run.py — starts the supervisor + 3 demo agents in one process,
prints all output including real sonar-pro interventions.
"""
import threading, time, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

# MUST load .env before any overseer import — config.py reads env at import time
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")  # explicit path, no ambiguity

# Sanity check
key = os.getenv("PERPLEXITY_API_KEY", "")
if not key:
    print("ERROR: PERPLEXITY_API_KEY not set — check .env", file=sys.stderr)
    sys.exit(1)
print(f"[env] API key loaded: {key[:12]}...", flush=True)

from overseer.supervisor import SupervisorThread
from overseer.config import AGENTS_DIR
from overseer.adapters.sdk import log_action


# ── Event callback ────────────────────────────────────────────────────────────
def on_event(event_type, agent_id, agent_state, analysis=None):
    if event_type == "intervention":
        a = analysis or {}
        print(
            f"\n  ████  OVERSEER INTERVENED  [{agent_id}]\n"
            f"        Status:       {a.get('status','?')}\n"
            f"        Pattern:      {a.get('pattern','?')}\n"
            f"        Confidence:   {round(a.get('confidence',0)*100)}%\n"
            f"        Strategy:     {a.get('intervention','?')}\n"
            f"        Tokens saved: {a.get('tokens_wasted_estimate',0):,}\n"
            f"        Message:      {a.get('message','')[:140]}\n",
            flush=True,
        )


# ── Agent helpers ─────────────────────────────────────────────────────────────
def init_agent(agent_id, task):
    d = AGENTS_DIR / agent_id
    d.mkdir(parents=True, exist_ok=True)
    ap = d / "actions.jsonl"
    if ap.exists():
        ap.unlink()
    (d / "meta.json").write_text(json.dumps({
        "agent_id": agent_id, "task": task,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"
    }, indent=2))


def set_status(agent_id, status):
    p = AGENTS_DIR / agent_id / "meta.json"
    if p.exists():
        m = json.loads(p.read_text())
        m["status"] = status
        p.write_text(json.dumps(m, indent=2))


def check_iv(agent_id):
    p = AGENTS_DIR / agent_id / "intervention.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        if not d.get("consumed"):
            d["consumed"] = True
            p.write_text(json.dumps(d, indent=2))
            return d
    except Exception:
        pass
    return None


# ── Agent C: Doc Updater — finishes cleanly ───────────────────────────────────
def run_agent_c():
    aid = "doc-updater"
    init_agent(aid, "Update API documentation for auth endpoints")
    print(f"[{aid}] started", flush=True)
    steps = [
        ("Read",  "docs/api/auth.md",           640),
        ("Read",  "src/auth/token.ts",           980),
        ("Write", "docs/api/auth.md — updated",  300),
        ("Write", "docs/api/refresh.md — new",   300),
        ("Bash",  "markdownlint docs/",          420),
    ]
    for tool, key, tok in steps:
        log_action(aid, tool, key, tok)
        print(f"  [{aid}] {tool}: {key}", flush=True)
        time.sleep(1.2)
    set_status(aid, "completed")
    print(f"  [{aid}] ✓ Done — docs updated\n", flush=True)


# ── Agent B: Test Writer — steady progress ────────────────────────────────────
def run_agent_b():
    aid = "test-writer"
    init_agent(aid, "Write integration tests for the auth module")
    print(f"[{aid}] started", flush=True)
    steps = [
        ("Read",  "src/auth/token.ts",                         980),
        ("Read",  "src/auth/refresh.ts",                       760),
        ("Write", "tests/auth/token.test.ts — scaffold",       400),
        ("Bash",  "npx jest tests/auth/token.test.ts",         820),
        ("Edit",  "tests/auth/token.test.ts — add expiry case",350),
        ("Bash",  "npx jest tests/auth/token.test.ts",         820),
        ("Write", "tests/auth/refresh.test.ts — scaffold",     400),
        ("Edit",  "tests/auth/refresh.test.ts — add cases",    350),
        ("Bash",  "npx jest tests/auth/",                      900),
        ("Write", "tests/auth/middleware.test.ts",             400),
        ("Bash",  "npx jest tests/auth/ --coverage",           950),
    ]
    for tool, key, tok in steps:
        log_action(aid, tool, key, tok)
        print(f"  [{aid}] {tool}: {key}", flush=True)
        time.sleep(2.2)
    set_status(aid, "completed")
    print(f"  [{aid}] ✓ Done — all tests written\n", flush=True)


# ── Agent A: Auth Fixer — LOOPS, should be caught ────────────────────────────
def run_agent_a():
    aid = "auth-fixer"
    init_agent(aid, "Fix token expiry bug in src/auth/token.ts")
    print(f"[{aid}] started", flush=True)

    # Phase 1: reasonable exploration
    phase1 = [
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/refresh.ts",          980),
        ("Bash", "grep -r refreshToken src/",    720),
        ("Read", "src/middleware/auth.ts",        860),
    ]
    for tool, key, tok in phase1:
        log_action(aid, tool, key, tok)
        print(f"  [{aid}] {tool}: {key}", flush=True)
        time.sleep(1.5)

    # Phase 2: loop — same reads, no edits
    print(f"\n  [{aid}] >>> entering loop — repeated reads, no edits <<<\n", flush=True)
    loop_actions = [
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/token.ts",          1240),
        ("Read", "src/auth/refresh.ts",          980),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r refreshToken src/",   720),
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/refresh.ts",          980),
    ]
    for tool, key, tok in loop_actions:
        iv = check_iv(aid)
        if iv:
            itype = iv.get("type", "?")
            msg   = iv.get("message") or iv.get("revised_prompt", "")
            print(f"\n  [{aid}] 🛑 INTERVENTION RECEIVED ({itype})", flush=True)
            print(f"  [{aid}]    → {msg[:160]}\n", flush=True)
            log_action(aid, "Edit", "src/auth/token.ts — refreshBuffer: 30s → 300s", 400)
            log_action(aid, "Bash", "npm test src/auth/", 600)
            print(f"  [{aid}] ✓ Fix applied — tests passing", flush=True)
            set_status(aid, "completed")
            return

        log_action(aid, tool, key, tok)
        print(f"  [{aid}] {tool}: {key}  ← LOOP", flush=True)
        time.sleep(2.0)

    set_status(aid, "completed")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("  OVERSEER LIVE DEMO  —  sonar-pro watching 3 real agents")
    print("=" * 65)
    print("  Agent A  auth-fixer   LOOPS  (Overseer should intervene)")
    print("  Agent B  test-writer  progressing steadily")
    print("  Agent C  doc-updater  completes fast")
    print("=" * 65 + "\n")

    # Start supervisor (polls every 5s — fast enough to catch the loop)
    supervisor = SupervisorThread(on_event=on_event, interval=5)
    supervisor.start()
    print("[overseer] Supervisor started — polling every 5s\n", flush=True)
    time.sleep(1)

    # Start agents
    threads = [
        threading.Thread(target=run_agent_c, daemon=True),
        threading.Thread(target=run_agent_b, daemon=True),
        threading.Thread(target=run_agent_a, daemon=True),
    ]
    for t in threads:
        t.start()
        time.sleep(0.4)
    for t in threads:
        t.join(timeout=120)

    # Let last supervisor poll fire
    time.sleep(6)

    # Final summary
    state = supervisor.get_state()
    print("\n" + "=" * 65)
    print("  FINAL STATE")
    print("=" * 65)
    for aid, a in state["agents"].items():
        print(f"  {aid:20} status={a['status']:12} interventions={a['interventions']}  tokens_saved={a['tokens_saved']:,}")
    print(f"\n  Total interventions : {state['total_interventions']}")
    print(f"  Total tokens saved  : {state['total_tokens_saved']:,}")
    print()
