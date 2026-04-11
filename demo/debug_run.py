"""
debug_run.py — runs auth-fixer loop agent and calls analyze_agent() directly
so we can see exactly what sonar-pro returns and whether interventions fire.
"""
import threading, time, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

key = os.getenv("PERPLEXITY_API_KEY", "")
print(f"[env] key={key[:12]}...\n", flush=True)

from overseer.config import AGENTS_DIR, PERPLEXITY_API_KEY, MIN_ACTIONS, MIN_CONFIDENCE
from overseer.adapters.sdk import log_action
from overseer.adapters.file_watcher import get_action_window, get_action_count, get_agent_meta
from overseer.agent import analyze_agent
from overseer.interventions import dispatch

print(f"[config] PERPLEXITY_API_KEY in module = {PERPLEXITY_API_KEY[:12]}...", flush=True)
print(f"[config] MIN_ACTIONS={MIN_ACTIONS}  MIN_CONFIDENCE={MIN_CONFIDENCE}\n", flush=True)

# ── Init agent ────────────────────────────────────────────────────────────────
AID  = "auth-fixer-debug"
TASK = "Fix token expiry bug in src/auth/token.ts"

d = AGENTS_DIR / AID
d.mkdir(parents=True, exist_ok=True)
ap = d / "actions.jsonl"
if ap.exists(): ap.unlink()
(d / "meta.json").write_text(json.dumps({
    "agent_id": AID, "task": TASK,
    "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"
}, indent=2))

def write_action(tool, key_str, tok):
    log_action(AID, tool, key_str, tok)
    print(f"  [agent] {tool}: {key_str}", flush=True)
    time.sleep(0.3)

# ── Write 5 healthy actions ───────────────────────────────────────────────────
print("=== Phase 1: healthy exploration ===", flush=True)
write_action("Read", "src/auth/token.ts", 1240)
write_action("Bash", "grep -r tokenExpiry src/", 680)
write_action("Read", "src/auth/refresh.ts", 980)
write_action("Bash", "grep -r refreshToken src/", 720)
write_action("Read", "src/middleware/auth.ts", 860)

# ── Write 8 loop actions ──────────────────────────────────────────────────────
print("\n=== Phase 2: looping ===", flush=True)
for tool, key_str, tok in [
    ("Read", "src/auth/token.ts", 1240),
    ("Bash", "grep -r tokenExpiry src/", 680),
    ("Read", "src/auth/token.ts", 1240),
    ("Read", "src/auth/refresh.ts", 980),
    ("Bash", "grep -r tokenExpiry src/", 680),
    ("Read", "src/auth/token.ts", 1240),
    ("Bash", "grep -r refreshToken src/", 720),
    ("Read", "src/auth/token.ts", 1240),
]:
    write_action(tool, key_str, tok)

# ── Now call analyze_agent directly and inspect output ───────────────────────
print("\n=== Calling sonar-pro directly ===", flush=True)
actions = get_action_window(AID)
count   = get_action_count(AID)
print(f"  Actions in window: {count}", flush=True)
print(f"  Window size sent:  {len(actions)}", flush=True)
print(f"  Sending to sonar-pro...", flush=True)

analysis = analyze_agent(AID, TASK, actions)

print(f"\n  ── sonar-pro response ──", flush=True)
for k, v in analysis.items():
    print(f"    {k:25} = {v}", flush=True)

# ── Dispatch if warranted ─────────────────────────────────────────────────────
if analysis["status"] != "healthy" and analysis["intervention"] != "none":
    print(f"\n  >>> DISPATCHING intervention: {analysis['intervention']}", flush=True)
    result = dispatch(AID, analysis)
    print(f"  >>> dispatch result: {result}", flush=True)

    # Check the file was written
    iv_path = AGENTS_DIR / AID / "intervention.json"
    if iv_path.exists():
        print(f"\n  >>> intervention.json written:", flush=True)
        print(f"      {iv_path.read_text()[:300]}", flush=True)
else:
    print(f"\n  >>> No intervention fired (status={analysis['status']}, intervention={analysis['intervention']})", flush=True)
