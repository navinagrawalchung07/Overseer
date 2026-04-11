"""
demo/demo_seed.py

One-command live demo. Run this while `overseer dashboard` is open.
Three agents appear immediately and play out in real time:

  auth-fixer   → loops on the same files → Overseer catches it
  test-writer  → makes steady progress → completes cleanly
  doc-updater  → finishes fast → goes green

Usage:
    # Terminal 1
    overseer dashboard

    # Terminal 2
    python demo/demo_seed.py
"""
import json
import time
import threading
import sys
from pathlib import Path
from datetime import datetime, timezone

# Allow running from project root without install
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from overseer.config import AGENTS_DIR
from overseer.adapters.sdk import log_action


# ── Helpers ───────────────────────────────────────────────────────────────────

def _init(agent_id, task):
    d = AGENTS_DIR / agent_id
    d.mkdir(parents=True, exist_ok=True)
    ap = d / "actions.jsonl"
    if ap.exists():
        ap.unlink()
    (d / "meta.json").write_text(json.dumps({
        "agent_id":   agent_id,
        "task":       task,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status":     "running",
    }, indent=2))
    print(f"  ▶  {agent_id} started", flush=True)


def _done(agent_id):
    p = AGENTS_DIR / agent_id / "meta.json"
    if p.exists():
        m = json.loads(p.read_text())
        m["status"] = "completed"
        p.write_text(json.dumps(m, indent=2))
    print(f"  ✓  {agent_id} completed\n", flush=True)


def _check_iv(agent_id):
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


def _act(agent_id, tool, key, tokens, label=""):
    log_action(agent_id, tool, key, tokens)
    tag = f"  ← {label}" if label else ""
    print(f"     [{agent_id}]  {tool:6}  {key}{tag}", flush=True)


# ── Agent A: auth-fixer — LOOPS, gets caught ──────────────────────────────────

def run_auth_fixer():
    aid  = "auth-fixer"
    task = "Fix token expiry bug in src/auth/token.ts"
    _init(aid, task)
    time.sleep(0.5)

    # Phase 1: reasonable exploration
    for tool, key, tok in [
        ("Read", "src/auth/token.ts",         1240),
        ("Bash", "grep -r tokenExpiry src/",   680),
        ("Read", "src/auth/refresh.ts",         980),
        ("Bash", "grep -r refreshToken src/",   720),
        ("Read", "src/middleware/auth.ts",       860),
    ]:
        _act(aid, tool, key, tok)
        time.sleep(1.8)

    # Phase 2: loop — same files, no edits
    print(f"\n     [{aid}]  >>> looping — reads with no edits <<<\n", flush=True)
    loop = [
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/token.ts",          1240),
        ("Read", "src/auth/refresh.ts",         980),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r refreshToken src/",   720),
        ("Read", "src/auth/token.ts",          1240),
        ("Bash", "grep -r tokenExpiry src/",    680),
        ("Read", "src/auth/refresh.ts",         980),
    ]
    for tool, key, tok in loop:
        iv = _check_iv(aid)
        if iv:
            itype = iv.get("type", "?")
            msg   = iv.get("message") or iv.get("revised_prompt", "")
            print(f"\n     [{aid}]  🛑  OVERSEER INTERVENED  ({itype})", flush=True)
            print(f"     [{aid}]     → {msg[:160]}\n", flush=True)
            # Agent recovers — write the fix
            _act(aid, "Edit", "src/auth/token.ts — refreshBuffer: 30s → 300s", 400)
            time.sleep(0.8)
            _act(aid, "Bash", "npm test src/auth/", 600)
            time.sleep(0.8)
            _done(aid)
            return

        _act(aid, tool, key, tok, "LOOP")
        time.sleep(2.2)

    _done(aid)


# ── Agent B: test-writer — steady progress ────────────────────────────────────

def run_test_writer():
    aid  = "test-writer"
    task = "Write integration tests for the auth module"
    _init(aid, task)
    time.sleep(0.5)

    for tool, key, tok in [
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
    ]:
        _act(aid, tool, key, tok)
        time.sleep(2.5)

    _done(aid)


# ── Agent C: doc-updater — finishes fast ──────────────────────────────────────

def run_doc_updater():
    aid  = "doc-updater"
    task = "Update API documentation for auth endpoints"
    _init(aid, task)
    time.sleep(0.5)

    for tool, key, tok in [
        ("Read",  "docs/api/auth.md",          640),
        ("Read",  "src/auth/token.ts",          980),
        ("Write", "docs/api/auth.md — updated", 300),
        ("Write", "docs/api/refresh.md — new",  300),
        ("Bash",  "markdownlint docs/",         420),
    ]:
        _act(aid, tool, key, tok)
        time.sleep(1.4)

    _done(aid)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  OVERSEER LIVE DEMO")
    print("=" * 60)
    print("  Make sure `overseer dashboard` is running in another terminal.")
    print("  Open http://localhost:7860 to watch in real time.\n")
    print("  Agents:")
    print("    auth-fixer   will LOOP  →  Overseer intervenes")
    print("    test-writer  progressing steadily")
    print("    doc-updater  completes fast")
    print("=" * 60 + "\n")

    # Clear any stale state
    import shutil
    agents_dir = AGENTS_DIR
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
    agents_dir.mkdir(parents=True, exist_ok=True)

    threads = [
        threading.Thread(target=run_doc_updater,  daemon=True),
        threading.Thread(target=run_test_writer,  daemon=True),
        threading.Thread(target=run_auth_fixer,   daemon=True),
    ]
    for t in threads:
        t.start()
        time.sleep(0.3)
    for t in threads:
        t.join(timeout=180)

    print("\n" + "=" * 60)
    print("  Demo complete.")
    print("=" * 60 + "\n")
