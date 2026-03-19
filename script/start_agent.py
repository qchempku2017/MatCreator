#!/usr/bin/env python3
"""Start the MatCreator ADK web agent.

Determines the workspace root (via MATCLAW_WORKSPACE env var or ~/.workspace),
changes into it, then launches `adk web` pointing at the project agents directory.

Usage:
    python script/start_agent.py [OPTIONS]

Examples:
    python script/start_agent.py
    python script/start_agent.py --reload-agents
    python script/start_agent.py --port 8080 --host 0.0.0.0
    MATCLAW_WORKSPACE=/data/ws python script/start_agent.py
"""

import os
import subprocess
import sys
from pathlib import Path

import click

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
AGENTS_DIR = PROJECT_ROOT / "agents"


def _resolve_workspace() -> Path:
    """Resolve the workspace root using the same logic as workspace.py."""
    env_val = os.environ.get("MATCLAW_WORKSPACE", "")
    if env_val:
        return Path(env_val).expanduser().resolve()
    return Path.home() / ".workspace"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--reload-agents", is_flag=True, default=False,
              help="Enable live reload when agent files change.")
@click.option("--reload", is_flag=True, default=False,
              help="Enable auto-reload for the FastAPI server.")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Binding host for the ADK web server.")
@click.option("--port", default=8000, show_default=True, type=int,
              help="Port for the ADK web server.")
@click.option("--workspace", default=None, metavar="DIR",
              help="Override the workspace root directory (also settable via MATCLAW_WORKSPACE).")
@click.option("--log-level",
              type=click.Choice(["debug", "info", "warning", "error", "critical"],
                                case_sensitive=False),
              default="info", show_default=True,
              help="Logging level for the ADK server.")
@click.option("-v", "--verbose", is_flag=True, default=False,
              help="Shortcut for --log-level debug.")
def main(reload_agents, reload, host, port, workspace, log_level, verbose):
    """Start the MatCreator ADK web agent from the workspace directory."""
    # Determine workspace root
    if workspace:
        ws_root = Path(workspace).expanduser().resolve()
        os.environ["MATCLAW_WORKSPACE"] = str(ws_root)
    else:
        ws_root = _resolve_workspace()

    ws_root.mkdir(parents=True, exist_ok=True)
    click.echo(f"Workspace : {ws_root}")
    click.echo(f"Agents dir: {AGENTS_DIR}")

    os.chdir(ws_root)
    click.echo(f"Working directory changed to: {ws_root}\n")

    # Build adk web command
    cmd = [
        "adk", "web",
        str(AGENTS_DIR),
        "--host", host,
        "--port", str(port),
        "--log_level", "debug" if verbose else log_level,
    ]
    if reload_agents:
        cmd.append("--reload_agents")
    if reload:
        cmd.append("--reload")

    click.echo("Starting: " + " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        pass
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
