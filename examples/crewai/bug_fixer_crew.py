"""
examples/crewai/bug_fixer_crew.py

A real CrewAI bug-fixing crew instrumented with Overseer in two lines.

This example shows a two-agent crew:
  - Researcher: reads code, searches for context, diagnoses the bug
  - Engineer:   writes the fix based on the researcher's findings

Without Overseer, if the Researcher gets stuck reading the same file
repeatedly, you'd never know until you'd burned thousands of tokens.
With Overseer, the loop is detected and a corrective message is injected
before the next step.

Prerequisites:
    pip install crewai crewai-tools overseer-ai
    export PERPLEXITY_API_KEY=pplx-...
    export OPENAI_API_KEY=sk-...      # or set llm= to your preferred model

Run:
    # Terminal 1 — start Overseer supervisor
    overseer watch

    # Terminal 2 — run this crew
    python examples/crewai/bug_fixer_crew.py
"""

import os
from crewai import Agent, Task, Process
from crewai_tools import FileReadTool, DirectoryReadTool

# ── Overseer: two lines to instrument any CrewAI crew ────────────────────────
from overseer.adapters.crewai_adapter import overseer_crew
# That's it. Replace Crew(...) with overseer_crew(agent_id=..., task=..., ...)
# ─────────────────────────────────────────────────────────────────────────────


# ── Tools ─────────────────────────────────────────────────────────────────────
file_reader = FileReadTool()
dir_reader  = DirectoryReadTool()


# ── Agents ────────────────────────────────────────────────────────────────────
researcher = Agent(
    role="Senior Code Investigator",
    goal=(
        "Thoroughly investigate the token expiry bug in src/auth/. "
        "Identify the root cause by reading source files and tracing "
        "the issue to a specific line. Do NOT read the same file twice."
    ),
    backstory=(
        "You are a meticulous senior engineer who has debugged hundreds "
        "of authentication issues. You read code once, take careful notes, "
        "and move forward — you never re-read a file you have already seen."
    ),
    tools=[file_reader, dir_reader],
    verbose=True,
    max_iter=12,   # cap iterations so a loop can't run forever
)

engineer = Agent(
    role="Senior Software Engineer",
    goal=(
        "Write a clean, targeted fix for the token expiry bug based on "
        "the researcher's findings. Edit only the necessary files."
    ),
    backstory=(
        "You are a pragmatic engineer who writes minimal, well-tested fixes. "
        "You trust the researcher's diagnosis and act on it immediately."
    ),
    tools=[file_reader],
    verbose=True,
    max_iter=8,
)


# ── Tasks ─────────────────────────────────────────────────────────────────────
research_task = Task(
    description=(
        "Investigate the token expiry bug in the src/auth/ directory.\n\n"
        "Steps:\n"
        "1. List the files in src/auth/\n"
        "2. Read token.ts — note the refreshBuffer value and expiry logic\n"
        "3. Read refresh.ts — note how refresh tokens are validated\n"
        "4. Identify the root cause (likely a refreshBuffer window mismatch)\n"
        "5. Write a clear diagnosis: what is wrong and on which line\n\n"
        "IMPORTANT: Read each file at most once. Do not loop."
    ),
    expected_output=(
        "A concise diagnosis: which file, which line, what is wrong, "
        "and what the fix should be. Under 150 words."
    ),
    agent=researcher,
)

fix_task = Task(
    description=(
        "Apply the fix identified by the researcher.\n\n"
        "Based on the research output:\n"
        "1. Open the identified file\n"
        "2. Make the targeted change (update the refreshBuffer value)\n"
        "3. Verify the change looks correct\n"
        "4. Write a brief summary of what was changed and why"
    ),
    expected_output=(
        "Confirmation that the fix was applied, with the before/after "
        "diff and a one-sentence explanation."
    ),
    agent=engineer,
    context=[research_task],  # engineer reads researcher's output
)


# ── Intervention handler ──────────────────────────────────────────────────────
def handle_overseer_intervention(intervention: dict) -> None:
    """
    Called by Overseer when a loop is detected.

    In a production system you might:
    - Log to your observability platform
    - Send a Slack/PagerDuty alert
    - Store the intervention for post-run analysis

    Here we just print it clearly.
    """
    iv_type = intervention.get("type", "intervention")
    message = intervention.get("message") or intervention.get("revised_prompt", "")
    print("\n" + "=" * 70)
    print(f"🛑  OVERSEER INTERVENED  ({iv_type})")
    print("=" * 70)
    print(f"Message: {message}")
    print("=" * 70 + "\n")
    # Note: for inject_context, CrewAI will naturally pick up the corrective
    # message on the next step because the agent re-reads its context window.
    # For stop_and_restart you would call crew.kickoff() again with a
    # modified task description.


# ── Crew ──────────────────────────────────────────────────────────────────────
# This is the ONLY change vs. a standard CrewAI crew:
# Replace `Crew(...)` with `overseer_crew(agent_id=..., task=..., ...)`
crew = overseer_crew(
    agent_id="bug-fixer-crew",              # unique ID in Overseer
    task="Fix token expiry bug in src/auth/",  # shown in dashboard
    on_intervention=handle_overseer_intervention,

    # Everything below is standard crewai.Crew() kwargs — unchanged
    agents=[researcher, engineer],
    tasks=[research_task, fix_task],
    process=Process.sequential,
    verbose=True,
)


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n👁  Overseer is watching this crew.")
    print("   Run `overseer watch` in another terminal to see the dashboard.\n")

    result = crew.kickoff()

    print("\n" + "=" * 70)
    print("CREW RESULT")
    print("=" * 70)
    print(result)
