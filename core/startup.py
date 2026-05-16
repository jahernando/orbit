"""startup.py — interactive checks fired from the shell startup chain.

Three checks, each callable independently:

  startup_untracked_check  — stage tracked files; prompt about untracked.
  startup_commit_offer     — if anything is staged, offer to commit (+push).
  startup_code_update_check — fetch ORBIT_CODE and offer to pull/merge if behind.

Carved out of ``core/commit.py`` in v0.38: these are about *shell startup*,
not about the ``orbit commit`` command itself, and were only ever called
from ``core/shell.py``. ``commit.py`` retains the git primitives and
``run_commit``; this module composes them into startup-time prompts.
"""
import subprocess
import sys
from datetime import datetime

from core.config import ORBIT_HOME as ORBIT_DIR
from core.commit import (
    _git_status,
    _git_commit,
    _git_add_all_tracked,
    _prompt_untracked,
    _can_push,
    _git_push,
)


# ── Code update check ────────────────────────────────────────────────────────

def _code_commits_behind() -> int:
    """Fetch origin in ORBIT_CODE and return how many commits we are behind.

    Returns 0 if up-to-date, not a git repo, or on error.
    """
    from core.config import ORBIT_CODE
    code_dir = str(ORBIT_CODE)
    try:
        rc = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True, cwd=code_dir,
        )
        if rc.returncode != 0:
            return 0

        rc = subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True, cwd=code_dir,
        )
        if rc.returncode != 0:
            return 0

        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True, text=True, cwd=code_dir,
        )
        if result.returncode != 0:
            return 0
        return int(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        return 0


def startup_code_update_check() -> None:
    """Check for code updates in the orbit code repo and offer to pull.

    Works in two modes:
    - Separated: ORBIT_CODE != ORBIT_HOME → check origin in ORBIT_CODE
    - Combined: ORBIT_CODE == ORBIT_HOME with 'public' remote → check public remote
    """
    from core.config import ORBIT_CODE
    code_dir = str(ORBIT_CODE)

    # Separated mode: code repo is separate from data
    if str(ORBIT_CODE) != str(ORBIT_DIR):
        behind = _code_commits_behind()
        if behind == 0:
            return

        print(f"  🔄 {behind} commit{'s' if behind != 1 else ''} nuevo{'s' if behind != 1 else ''} en orbit código")
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "HEAD..origin/main"],
                capture_output=True, text=True, cwd=code_dir,
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines()[:5]:
                    print(f"      {line}")
                if behind > 5:
                    print(f"      ... y {behind - 5} más")
        except FileNotFoundError:
            pass

        print()
        if not sys.stdin.isatty():
            return

        try:
            ans = input("  ¿Actualizar código? [S/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if ans not in ("", "s", "si", "sí", "y", "yes"):
            return

        try:
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=code_dir,
            )
            if result.returncode == 0:
                print("  ✓ Código actualizado.")
            else:
                print("  ⚠️  Error en pull. Actualiza manualmente: cd ~/orbit && git pull")
        except FileNotFoundError:
            pass
        return

    # Combined mode: ORBIT_CODE == ORBIT_HOME, check 'public' remote
    try:
        result = subprocess.run(
            ["git", "remote"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if "public" not in result.stdout.splitlines():
            return
    except FileNotFoundError:
        return

    try:
        subprocess.run(
            ["git", "fetch", "public", "--quiet"],
            capture_output=True, cwd=ORBIT_DIR,
        )
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..public/main"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode != 0:
            return
        behind = int(result.stdout.strip())
    except (FileNotFoundError, ValueError):
        return

    if behind == 0:
        return

    print(f"  🔄 {behind} commit{'s' if behind != 1 else ''} nuevo{'s' if behind != 1 else ''} en orbit público")
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "HEAD..public/main"],
            capture_output=True, text=True, cwd=ORBIT_DIR,
        )
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().splitlines()[:5]:
                print(f"      {line}")
            if behind > 5:
                print(f"      ... y {behind - 5} más")
    except FileNotFoundError:
        pass

    print()
    if not sys.stdin.isatty():
        return

    try:
        ans = input("  ¿Merge desde public? [S/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if ans not in ("", "s", "si", "sí", "y", "yes"):
        return

    try:
        result = subprocess.run(
            ["git", "merge", "public/main", "--no-edit"],
            cwd=ORBIT_DIR,
        )
        if result.returncode == 0:
            print("  ✓ Merge desde public realizado.")
        else:
            print("  ⚠️  Error en merge. Resuelve conflictos manualmente.")
    except FileNotFoundError:
        pass


# ── Untracked + commit prompts ───────────────────────────────────────────────

def startup_untracked_check() -> None:
    """Stage tracked files and prompt to add untracked ones.

    Called early in the startup sequence so new files are staged
    before the commit prompt.
    """
    _git_add_all_tracked()
    _prompt_untracked()


def startup_commit_offer() -> None:
    """Show uncommitted changes and offer to commit + push.

    Called after untracked check so all staged files are visible.
    """
    status = [(c, p) for c, p in _git_status() if c != "??"]
    if not status:
        return

    n = len(status)
    print(f"  📌 {n} fichero{'s' if n != 1 else ''} modificado{'s' if n != 1 else ''} sin save")
    for code, path in status[:5]:
        print(f"      {code:<2}  {path}")
    if n > 5:
        print(f"      ... y {n - 5} más")
    print()

    default_msg = f"sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    can_push = _can_push()

    if not sys.stdin.isatty():
        return

    try:
        prompt = "  ¿Save + push?" if can_push else "  ¿Save?"
        raw = input(f"{prompt} [mensaje / Enter=\"{default_msg}\" / n]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if raw.lower() in ("n", "no"):
        return

    msg = raw if raw else default_msg

    rc = _git_commit(msg)
    if rc != 0:
        print("  ✗ Error al hacer el save.")
        return

    print(f"  ✓ Save: \"{msg}\"")

    from core.cloudsync import sync_to_cloud_background
    sync_to_cloud_background()

    if can_push:
        rc = _git_push()
        if rc == 0:
            print("  ✓ Push realizado.")
        else:
            print("  ⚠️  Error en push (puedes hacerlo manualmente con: git push)")
