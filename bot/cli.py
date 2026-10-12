from __future__ import annotations
import subprocess
import json
import sys
from pathlib import Path
import typer

app = typer.Typer(help="Option trading bot CLI")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _venv_python():
    v = PROJECT_ROOT / "venv" / "bin" / "python"
    return str(v) if v.exists() else sys.executable


@app.command()
def status():
    """Show bot status (calls run.py --status and pretty prints)."""
    p = subprocess.run([_venv_python(), str(PROJECT_ROOT / "run.py"), "--status"], capture_output=True, text=True)
    if p.returncode != 0:
        typer.secho("run.py --status failed:", fg=typer.colors.RED)
        typer.echo(p.stderr)
        raise typer.Exit(code=1)
    try:
        j = json.loads(p.stdout)
        typer.echo(json.dumps(j, indent=2))
    except Exception:
        typer.echo(p.stdout)


@app.command("once")
def run_once():
    """Run a single scan cycle (blocking)."""
    p = subprocess.run([_venv_python(), str(PROJECT_ROOT / "run.py"), "--once"])
    raise typer.Exit(code=p.returncode)


@app.command("start")
def start_loop(background: bool = typer.Option(False, help="Run bot loop in background using nohup")):
    """Start the run.py loop (non-daemon)."""
    if background:
        cmd = f"nohup {_venv_python()} {PROJECT_ROOT / 'run.py'} --loop > {PROJECT_ROOT / 'run.log'} 2>&1 & echo $!"
        p = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        typer.echo(f"Started background loop, pid: {p.stdout.strip()}")
    else:
        subprocess.run([_venv_python(), str(PROJECT_ROOT / "run.py"), "--loop"]) 


@app.command("stop")
def stop(pid: int = typer.Option(None, help="PID to kill. If omitted, will try to find run.py pid")):
    """Stop the running loop (by PID or auto-find)."""
    if pid:
        subprocess.run(["kill", str(pid)])
        typer.echo(f"killed {pid}")
        raise typer.Exit()
    p = subprocess.run(["pgrep", "-f", "run.py"], capture_output=True, text=True)
    if p.returncode != 0:
        typer.echo("No run.py process found")
        raise typer.Exit()
    for line in p.stdout.splitlines():
        subprocess.run(["kill", line])
        typer.echo(f"killed {line}")


@app.command()
def config_show():
    """Print the config.yaml"""
    cfg = PROJECT_ROOT / "config.yaml"
    typer.echo(cfg.read_text())
