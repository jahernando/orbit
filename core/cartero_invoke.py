"""Subprocess shim for the cartero satellite.

orbit never imports from satellites/cartero/ directly; this module is the
only bridge. The satellite lives under satellites/cartero/daemon.py and
exposes a CLI (--status/--stop/--start/--summary/--startup) consumed here.

Mirrors the pattern of views/ring/export.invoke_daemon for the ring satellite.
"""

import subprocess
import sys
from pathlib import Path

DAEMON_PATH = (Path(__file__).resolve().parent.parent
               / "satellites" / "cartero" / "daemon.py")


def run_mail(status: bool = False, stop: bool = False, start: bool = False,
             summary: bool = False) -> int:
    """`orbit mail` dispatcher — forwards flags to the satellite. Returns exit code."""
    cmd = [sys.executable, str(DAEMON_PATH)]
    if status:  cmd.append("--status")
    if stop:    cmd.append("--stop")
    if start:   cmd.append("--start")
    if summary: cmd.append("--summary")
    return subprocess.run(cmd).returncode


def startup_cartero() -> None:
    """Shell-startup hook — synchronous so initial mail status appears.

    The satellite double-forks internally to detach the long-running poll
    loop, so this returns quickly after the initial status printout.
    """
    subprocess.run([sys.executable, str(DAEMON_PATH), "--startup"])
