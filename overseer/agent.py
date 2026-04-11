"""
overseer/agent.py

Calls Perplexity sonar-pro to analyze an agent's action window.
Returns structured detection result. Uses JSON output mode since
Perplexity does not support forced tool_choice.
"""
import json
import re
from openai import OpenAI
from overseer.config import PERPLEXITY_API_KEY, PERPLEXITY_BASE_URL, AGENT_MODEL, MIN_CONFIDENCE

client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url=PERPLEXITY_BASE_URL)

SYSTEM_PROMPT = """\
You are Overseer, a supervisor AI that monitors AI coding agents for wasteful patterns.

You receive the recent action log of an agent working on a task. Determine whether the agent is:
1. healthy   — making genuine progress
2. looping   — repeating the same actions (same file reads, same greps) with no edits or writes
3. drifting  — taking actions unrelated to the original task
4. stalled   — no meaningful forward progress

Intervention strategies:
- none            → agent is healthy, do nothing
- inject_context  → feed a short corrective message to reorient the agent
- stop_and_restart → kill and relaunch with a revised prompt
- escalate        → flag for human review (ambiguous or high-stakes)

Rules:
- Confidence threshold for intervention: 0.78. Do not intervene below this.
- Reading the same file 3+ times with zero writes/edits in between is a clear loop.
- Running the same grep/bash command 3+ times is a loop.
- Do not interrupt healthy exploration (reading different files, making edits).

Respond ONLY with a JSON object — no markdown, no explanation, just the JSON:
{
  "status": "healthy" | "looping" | "drifting" | "stalled",
  "confidence": 0.0-1.0,
  "pattern": "short description of what you observed",
  "intervention": "none" | "inject_context" | "stop_and_restart" | "escalate",
  "message": "corrective message to inject (under 80 words, direct and specific)",
  "tokens_wasted_estimate": <integer>
}
"""


def analyze_agent(agent_id: str, task: str, actions: list[dict]) -> dict:
    """
    Send agent action window to Perplexity sonar-pro. Returns analysis dict.
    Never raises — returns healthy on any error.
    """
    if not PERPLEXITY_API_KEY:
        return _healthy("no_api_key")

    lines = []
    for i, a in enumerate(actions, 1):
        lines.append(
            f"{i:2}. [{a.get('tool','?'):14}] {a.get('key', a.get('action','?'))[:80]}"
            f"  ({a.get('tokens', '?')} tok)"
        )
    summary = "\n".join(lines)

    try:
        resp = client.chat.completions.create(
            model=AGENT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Agent ID: {agent_id}\n"
                    f"Task: {task}\n\n"
                    f"Recent actions ({len(actions)}):\n{summary}\n\n"
                    f"Analyze this agent and return the JSON object."
                )},
            ],
            temperature=0.1,
            max_tokens=400,
        )

        raw = resp.choices[0].message.content.strip()

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        result = json.loads(raw)

        # Enforce confidence threshold
        if result.get("confidence", 0) < MIN_CONFIDENCE:
            result["intervention"] = "none"
            result["status"] = "healthy"

        # Ensure all required keys exist
        result.setdefault("status", "healthy")
        result.setdefault("confidence", 0.0)
        result.setdefault("pattern", "")
        result.setdefault("intervention", "none")
        result.setdefault("message", "")
        result.setdefault("tokens_wasted_estimate", 0)

        return result

    except json.JSONDecodeError as e:
        return _healthy(f"json_parse_error:{str(e)[:60]}")
    except Exception as e:
        return _healthy(f"api_error:{str(e)[:80]}")


def _healthy(reason: str = "") -> dict:
    return {
        "status": "healthy",
        "confidence": 0.0,
        "pattern": reason,
        "intervention": "none",
        "message": "",
        "tokens_wasted_estimate": 0,
    }
