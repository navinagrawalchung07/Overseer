import os
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
HOME_DIR     = Path.home() / ".overseer"
AGENTS_DIR   = HOME_DIR / "agents"
HISTORY_FILE = HOME_DIR / "history.json"
STATE_FILE   = HOME_DIR / "state.json"

# ── Perplexity ──────────────────────────────────────────────────────────────
PERPLEXITY_API_KEY  = os.getenv("PERPLEXITY_API_KEY", "")
PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
AGENT_MODEL         = "sonar-pro"

# ── Supervisor tuning ───────────────────────────────────────────────────────
POLL_INTERVAL     = int(os.getenv("OVERSEER_POLL_INTERVAL", "10"))   # seconds
WINDOW_SIZE       = int(os.getenv("OVERSEER_WINDOW", "15"))          # actions to analyze
MIN_ACTIONS       = int(os.getenv("OVERSEER_MIN_ACTIONS", "4"))      # min before analysis
MIN_CONFIDENCE    = float(os.getenv("OVERSEER_CONFIDENCE", "0.78"))  # intervention threshold
HEURISTIC_REPEAT  = int(os.getenv("OVERSEER_HEURISTIC_REPEAT", "3"))

# ── Dashboard ───────────────────────────────────────────────────────────────
DASHBOARD_PORT = int(os.getenv("OVERSEER_PORT", "7860"))
