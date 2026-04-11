"""
overseer/cli.py

CLI: overseer watch | status | history | dashboard
"""
import json
import sys
import time
import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich import box

console = Console()


@click.group()
def cli():
    """Overseer — supervise your AI agents. Stop loops before they cost you."""
    pass


# ── watch ────────────────────────────────────────────────────────────────────
@cli.command()
@click.option("--interval", default=10, help="Poll interval in seconds")
@click.option("--agents", default=None, help="Path to agents directory (default: ~/.overseer/agents)")
def watch(interval, agents):
    """Start the supervisor. Watches all agents and intervenes on loops."""
    from overseer.config import AGENTS_DIR, PERPLEXITY_API_KEY
    from overseer.supervisor import SupervisorThread, load_state

    if agents:
        import overseer.config as cfg
        cfg.AGENTS_DIR = Path(agents)

    if not PERPLEXITY_API_KEY:
        console.print("[red]✗ PERPLEXITY_API_KEY not set. Run: export PERPLEXITY_API_KEY=pplx-...[/red]")
        sys.exit(1)

    console.print(Panel.fit(
        "[bold green]👁  Overseer is watching[/bold green]\n\n"
        f"Poll interval: [cyan]{interval}s[/cyan]\n"
        f"Agents dir:    [dim]{AGENTS_DIR}[/dim]\n\n"
        "Ctrl+C to stop.",
        border_style="green",
        title="Overseer"
    ))

    events = []

    def on_event(event_type, agent_id, agent_state, analysis):
        if event_type == "intervention":
            status   = agent_state.get("status", "?")
            strategy = agent_state.get("last_event", {}).get("type", "?")
            tokens   = agent_state.get("last_event", {}).get("tokens_saved", 0)
            console.print(
                f"\n[red bold]🚨 INTERVENTION[/red bold]  "
                f"[yellow]{agent_id}[/yellow]  "
                f"[dim]{status} → {strategy}[/dim]  "
                f"[green]{tokens:,} tokens saved[/green]"
            )

    state = load_state()
    supervisor = None

    try:
        from overseer.supervisor import poll_once
        while True:
            state = poll_once(state, on_event)
            _render_status(state)
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Overseer stopped.[/dim]")


def _render_status(state: dict):
    agents = state.get("agents", {})
    if not agents:
        console.print("[dim]No agents found. Start an agent simulation first.[/dim]")
        return

    t = Table(box=box.SIMPLE, show_header=True, header_style="bold dim")
    t.add_column("Agent",          width=20)
    t.add_column("Task",           width=32)
    t.add_column("Status",         width=14)
    t.add_column("Actions",        justify="right", width=8)
    t.add_column("Interventions",  justify="right", width=13)
    t.add_column("Tokens Saved",   justify="right", width=12)

    STATUS_COLORS = {
        "healthy":    "[green]● healthy[/green]",
        "looping":    "[red]● looping[/red]",
        "drifting":   "[yellow]● drifting[/yellow]",
        "stalled":    "[yellow]● stalled[/yellow]",
        "completed":  "[dim]✓ done[/dim]",
        "warming_up": "[dim]◌ warming[/dim]",
    }

    for agent_id, a in agents.items():
        status_str = STATUS_COLORS.get(a.get("status", "?"), a.get("status", "?"))
        t.add_row(
            agent_id[:20],
            a.get("task", "")[:32],
            status_str,
            str(a.get("action_count", 0)),
            str(a.get("interventions", 0)),
            f"{a.get('tokens_saved', 0):,}",
        )

    console.print(t)


# ── status ───────────────────────────────────────────────────────────────────
@cli.command()
def status():
    """Show current agent status."""
    from overseer.supervisor import load_state
    _render_status(load_state())


# ── history ──────────────────────────────────────────────────────────────────
@cli.command()
@click.option("--limit", default=20, help="Number of recent events")
def history(limit):
    """Show recent intervention history."""
    from overseer.supervisor import load_history
    events = load_history()[-limit:]

    if not events:
        console.print("[dim]No interventions yet.[/dim]")
        return

    t = Table(title="Intervention History", box=box.SIMPLE)
    t.add_column("Time",         style="dim",    width=18)
    t.add_column("Agent",        width=18)
    t.add_column("Status",       style="yellow", width=12)
    t.add_column("Strategy",     style="cyan",   width=16)
    t.add_column("Tokens Saved", justify="right")
    t.add_column("Pattern",      style="dim")

    for e in reversed(events):
        ts = e.get("timestamp", "")[:16].replace("T", " ")
        t.add_row(
            ts,
            e.get("agent_id", "")[:18],
            e.get("status", ""),
            e.get("intervention", ""),
            f"{e.get('tokens_saved', 0):,}",
            e.get("pattern", "")[:40],
        )
    console.print(t)


# ── dashboard ────────────────────────────────────────────────────────────────
@cli.command()
@click.option("--port", default=7860, help="Port to serve dashboard on")
def dashboard(port):
    """Launch the Overseer web dashboard."""
    import uvicorn
    console.print(Panel.fit(
        f"[bold green]👁  Overseer Dashboard[/bold green]\n\n"
        f"Open: [cyan]http://localhost:{port}[/cyan]",
        border_style="green"
    ))
    uvicorn.run("overseer.server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    cli()
