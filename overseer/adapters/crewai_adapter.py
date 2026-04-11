"""
overseer/adapters/crewai_adapter.py

CrewAI adapter for Overseer — Level 2 instrumentation.

Provides two integration points:

  1. OverseerStepCallback — drop-in step_callback for any Crew.
     Intercepts every agent action (ToolResult, AgentAction, AgentFinish)
     and logs it to Overseer automatically.

  2. overseer_crew() — factory wrapper around Crew() that wires up
     the callback and registers the agent with Overseer in one line.

Usage (see examples/crewai/bug_fixer_crew.py for full working example):

    from overseer.adapters.crewai_adapter import overseer_crew

    crew = overseer_crew(
        agent_id="bug-fixer",
        task="Fix the token expiry bug in src/auth/",
        agents=[researcher, coder],
        tasks=[research_task, fix_task],
    )
    crew.kickoff()
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from overseer.adapters.sdk import log_action, _init_agent, _check_intervention
from overseer.config import AGENTS_DIR


# ── Step callback ─────────────────────────────────────────────────────────────

class OverseerStepCallback:
    """
    Drop-in step_callback for CrewAI Crew/Agent.

    CrewAI calls this after every agent step with one of:
      - AgentAction (tool was invoked)
      - ToolResult   (tool returned output)
      - AgentFinish  (agent produced final answer)

    We log tool invocations to Overseer and check for pending
    interventions after each step.

    Args:
        agent_id:     Overseer agent identifier (must be unique per run)
        on_intervention: optional callable(dict) fired when Overseer
                         has an intervention ready
    """

    def __init__(self, agent_id: str, on_intervention=None):
        self.agent_id        = agent_id
        self.on_intervention = on_intervention

    def __call__(self, step_output: Any) -> None:
        self._log_step(step_output)
        self._check()

    def _log_step(self, step: Any) -> None:
        type_name = type(step).__name__

        if type_name == "AgentAction":
            # Agent decided to call a tool
            tool   = getattr(step, "tool", "UnknownTool")
            inp    = getattr(step, "tool_input", "")
            key    = f"{tool}: {str(inp)[:80]}"
            tokens = _estimate_tokens(tool, inp)
            log_action(self.agent_id, tool, key, tokens)

        elif type_name == "ToolResult":
            # Tool returned a result — log the result size as token cost
            tool   = getattr(step, "tool", "ToolResult")
            result = getattr(step, "result", "")
            tokens = max(200, len(str(result)) // 4)
            log_action(self.agent_id, f"{tool}:result", str(result)[:80], tokens)

        elif type_name == "AgentFinish":
            # Agent produced its final answer
            log_action(self.agent_id, "AgentFinish", "final answer produced", 200)

        # Unknown step type — log generically
        else:
            log_action(self.agent_id, type_name, str(step)[:80], 300)

    def _check(self) -> None:
        """Check for a pending Overseer intervention and fire the callback."""
        iv = _check_intervention(self.agent_id)
        if iv and self.on_intervention:
            self.on_intervention(iv)


# ── Task callback ─────────────────────────────────────────────────────────────

class OverseerTaskCallback:
    """
    Drop-in task_callback for CrewAI Crew.

    Called after each Task completes with a TaskOutput object.
    Logs task completion and resets the action window so Overseer
    doesn't carry over old context into the next task.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id

    def __call__(self, task_output: Any) -> None:
        description = getattr(task_output, "description", "task")
        log_action(self.agent_id, "TaskComplete", str(description)[:80], 0)


# ── Factory wrapper ───────────────────────────────────────────────────────────

def overseer_crew(
    agent_id: str,
    task: str,
    on_intervention=None,
    **crew_kwargs,
):
    """
    Drop-in replacement for crewai.Crew() that wires up Overseer automatically.

    Args:
        agent_id:        unique identifier for this agent run in Overseer
        task:            human-readable task description shown in the dashboard
        on_intervention: optional callable(dict) called when Overseer intervenes
        **crew_kwargs:   all normal crewai.Crew() keyword arguments

    Returns:
        A crewai.Crew instance with step_callback and task_callback pre-wired.

    Example:
        crew = overseer_crew(
            agent_id="bug-fixer",
            task="Fix the token expiry bug in src/auth/",
            agents=[researcher, coder],
            tasks=[research_task, fix_task],
            process=Process.sequential,
            verbose=True,
        )
        crew.kickoff()
    """
    try:
        from crewai import Crew
    except ImportError:
        raise ImportError(
            "crewai is not installed. Run: pip install crewai"
        )

    # Register with Overseer before kickoff
    _init_agent(agent_id, task)

    step_cb = OverseerStepCallback(agent_id, on_intervention=on_intervention)
    task_cb = OverseerTaskCallback(agent_id)

    # Don't overwrite if the caller already set their own callbacks
    if "step_callback" not in crew_kwargs:
        crew_kwargs["step_callback"] = step_cb
    if "task_callback" not in crew_kwargs:
        crew_kwargs["task_callback"] = task_cb

    return Crew(**crew_kwargs)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_tokens(tool: str, tool_input: Any) -> int:
    """Rough token cost estimate for a tool invocation."""
    tool_lower = str(tool).lower()
    if "read" in tool_lower or "file" in tool_lower:
        return 1200
    if "search" in tool_lower or "web" in tool_lower:
        return 1500
    if "bash" in tool_lower or "command" in tool_lower or "terminal" in tool_lower:
        return 800 + len(str(tool_input)) // 4
    if "write" in tool_lower or "edit" in tool_lower:
        return 400
    return 500
