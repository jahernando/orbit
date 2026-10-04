"""core.focus.modes — modos libre / plantilla / repetir, menú y selector."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from core.focus.common import (
    _RAILS,
    _RAIL_EMOJI,
    _RAIL_LABEL,
    _iso_week_label,
    _week_bounds,
    _week_file_path,
)
from core.focus.prompts import (
    _ask_yn,
    _create_block,
    _create_blocks_for_project,
    _list_available_projects,
    _resolve_project_name,
)
from core.focus.weekfile import (
    _append_blocks_to_week_file,
    _RAIL_FROM_EMOJI,
    _build_id_task_index,
    _parse_week_blocks_detailed,
    _parse_week_file,
    _regenerate_counter,
    _write_week_file,
)
from core.focus.year import _refresh_year_silent


def _run_mode_libre(mission_dir: Path, template: dict,
                    target: date, week_file: Path,
                    *,
                    initial_projects: Optional[dict[str, list[str]]] = None,
                    initial_blocks: Optional[dict[str, list[tuple[str, str]]]] = None,
                    initial_status: str = "normal") -> int:
    """Interactive free-mode planning. Asks projects/blocks rail by rail,
    creates the tasks in mission/agenda.md, writes the week file.

    Si se pasan ``initial_projects`` / ``initial_blocks``, se extienden
    (modo "añadir bloques" desde F7) preservando el contenido existente.
    """
    available = _list_available_projects(mission_dir)
    if not available:
        print("⚠️  No hay otros proyectos en el workspace para asignar a "
              "los carriles. Crea al menos uno con `orbit project new`.")
        return 1

    week_label = _iso_week_label(target)
    monday, _ = _week_bounds(target)
    duration = template["block_duration"]

    print(f"\nProyectos disponibles: {', '.join(available)}\n")

    rails_projects: dict[str, list[str]] = (
        {r: list(initial_projects.get(r, [])) for r in _RAILS}
        if initial_projects else {r: [] for r in _RAILS}
    )
    blocks_by_rail: dict[str, list[tuple[str, str]]] = (
        {r: list(initial_blocks.get(r, [])) for r in _RAILS}
        if initial_blocks else {r: [] for r in _RAILS}
    )
    pre_existing = sum(len(v) for v in blocks_by_rail.values())

    for rail in _RAILS:
        emoji = _RAIL_EMOJI[rail]
        label = _RAIL_LABEL[rail]
        print(f"{emoji} {label}")
        while True:
            try:
                raw = input(f"  proyecto (Enter para terminar {label}): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            if not raw:
                break
            canonical = _resolve_project_name(raw, available)
            if canonical is None:
                continue
            # Allow extending an already-listed project (add more blocks);
            # avoid duplicate header in rails_projects.
            if canonical not in rails_projects[rail]:
                rails_projects[rail].append(canonical)

            default_blocks = template["blocks_per_project"][rail]
            try:
                raw = input(f"    bloques [{default_blocks}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            try:
                n_blocks = int(raw) if raw else default_blocks
            except ValueError:
                print(f"    ⚠️  No es un entero: {raw!r} — usando {default_blocks}")
                n_blocks = default_blocks
            if n_blocks <= 0:
                continue

            blocks_by_rail[rail].extend(
                _create_blocks_for_project(canonical, rail, n_blocks,
                                            week_label, monday, duration))
        print()

    total = sum(len(v) for v in blocks_by_rail.values())
    new_total = total - pre_existing
    if new_total <= 0 and pre_existing == 0:
        print("⚠️  No se creó ningún bloque. Archivo semanal no escrito.")
        return 1

    if initial_blocks is not None and week_file.exists():
        # "añadir bloques": no reescribir la hoja (perdería retrospectiva,
        # símbolos con fecha y balance) — solo se insertan los nuevos.
        initial_ids = {oid for blocks in initial_blocks.values()
                       for _, oid in blocks}
        new_blocks = {r: [(p, oid) for p, oid in blocks_by_rail[r]
                          if oid not in initial_ids] for r in _RAILS}
        _append_blocks_to_week_file(week_file, rails_projects, new_blocks)
    else:
        _write_week_file(week_file, target, initial_status,
                         rails_projects, blocks_by_rail)
    if pre_existing:
        print(f"\n✓ {new_total} bloques añadidos · total semana: {total}")
    else:
        print(f"\n✓ {total} bloques creados en mission/agenda.md")
    print(f"✓ Archivo semanal: {week_file}")
    return 0


# ── Modo plantilla (F5) ───────────────────────────────────────────────────

def _prev_week_file(mission_dir: Path, target: date) -> Optional[Path]:
    """Return path to W-1 focus file if it exists, else None."""
    prev = target - timedelta(days=7)
    p = _week_file_path(mission_dir, prev)
    return p if p.exists() else None


def _extract_w_minus_1_projects(mission_dir: Path,
                                 target: date) -> dict[str, list[str]]:
    """Read W-1 file (if any) and return rail → [project names]."""
    out: dict[str, list[str]] = {r: [] for r in _RAILS}
    prev = _prev_week_file(mission_dir, target)
    if not prev:
        return out
    text = prev.read_text()
    # Look at the '## Carriles' section: '- ⚓ Anchor: [[proj-a]], [[proj-b]]'
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s == "## Carriles":
            in_section = True
            continue
        if in_section and s.startswith("## "):
            break
        if not in_section or not s.startswith("- "):
            continue
        for emoji, rail in _RAIL_FROM_EMOJI.items():
            if s.startswith(f"- {emoji}"):
                projs = re.findall(r"\[\[([^\]]+)\]\]", s)
                if projs:
                    out[rail] = projs
                break
    return out


def _prompt_project_with_default(label: str, idx: int, default: Optional[str],
                                  available: list[str]) -> Optional[str]:
    """Ask for a project, allowing Enter to accept the default. None to skip."""
    hint = f" [{default}]" if default else ""
    try:
        raw = input(f"  proyecto #{idx}{hint} (Enter "
                    f"{'acepta default' if default else 'salta'}): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return default
    return _resolve_project_name(raw, available)


def _run_mode_plantilla(mission_dir: Path, template: dict,
                        target: date, week_file: Path) -> int:
    """Plantilla-mode: usa template para cantidades; W-1 (si existe) para
    defaults de proyectos por carril.
    """
    available = _list_available_projects(mission_dir)
    if not available:
        print("⚠️  No hay otros proyectos en el workspace.")
        return 1

    week_label = _iso_week_label(target)
    monday, _ = _week_bounds(target)
    duration = template["block_duration"]
    prev_projects = _extract_w_minus_1_projects(mission_dir, target)
    if any(prev_projects.values()):
        print(f"  (defaults de W-1: " +
              "; ".join(f"{_RAIL_EMOJI[r]} {','.join(prev_projects[r]) or '—'}"
                         for r in _RAILS) + ")")
    print(f"  Proyectos disponibles: {', '.join(available)}\n")

    rails_projects: dict[str, list[str]] = {r: [] for r in _RAILS}
    blocks_by_rail: dict[str, list[tuple[str, str]]] = {r: [] for r in _RAILS}

    for rail in _RAILS:
        emoji = _RAIL_EMOJI[rail]
        label = _RAIL_LABEL[rail]
        lo, hi = template["projects_per_rail"][rail]
        n_blocks = template["blocks_per_project"][rail]
        rng = f"{lo}" if lo == hi else f"{lo}-{hi}"
        proj_word = "proyecto" if hi == 1 else "proyectos"
        blk_word = "bloque" if n_blocks == 1 else "bloques"
        print(f"{emoji} {label} — template: {rng} {proj_word} × "
              f"{n_blocks} {blk_word}")

        # Decide cuántos proyectos esta semana.
        if lo == hi:
            n_projects = lo
        else:
            try:
                raw = input(f"  cuántos proyectos [{hi}]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 1
            try:
                n_projects = int(raw) if raw else hi
            except ValueError:
                n_projects = hi
            n_projects = max(0, min(n_projects, len(available)))

        defaults = prev_projects.get(rail) or []
        for i in range(1, n_projects + 1):
            default = defaults[i - 1] if i - 1 < len(defaults) else None
            canonical = _prompt_project_with_default(label, i, default, available)
            if canonical is None:
                continue
            if canonical in rails_projects[rail]:
                print(f"    ⚠️  {canonical} ya está en {label} esta semana")
                continue
            rails_projects[rail].append(canonical)
            blocks_by_rail[rail].extend(
                _create_blocks_for_project(canonical, rail, n_blocks,
                                            week_label, monday, duration))
        print()

    total = sum(len(v) for v in blocks_by_rail.values())
    if total == 0:
        print("⚠️  No se creó ningún bloque. Archivo semanal no escrito.")
        return 1

    _write_week_file(week_file, target, "normal",
                     rails_projects, blocks_by_rail)
    print(f"\n✓ {total} bloques creados en mission/agenda.md")
    print(f"✓ Archivo semanal: {week_file}")
    return 0


def _run_mode_repetir(mission_dir: Path, template: dict,
                      target: date, week_file: Path) -> int:
    """Clone W-1: same rails / projects / slot offsets (+7 days)."""
    prev = _prev_week_file(mission_dir, target)
    if prev is None:
        print("⚠️  No existe la semana anterior, no se puede repetir.")
        return 1
    prev_blocks = _parse_week_blocks_detailed(prev.read_text())
    if not prev_blocks:
        print(f"⚠️  {prev.name} no contiene bloques.")
        return 1

    id_index = _build_id_task_index(mission_dir)
    available = set(_list_available_projects(mission_dir))
    week_label = _iso_week_label(target)

    # Build the clone plan: (rail, project, new_date, time).
    plan: list[tuple[str, str, str, str]] = []
    skipped: list[str] = []
    for rail, proj, oid in prev_blocks:
        if proj not in available:
            skipped.append(f"{_RAIL_EMOJI[rail]} {proj} (proyecto ausente)")
            continue
        t = id_index.get(oid)
        if not t or not t.get("date") or not t.get("time"):
            skipped.append(f"{_RAIL_EMOJI[rail]} {proj} [orbit:{oid}] "
                           f"(sin date/time en agenda)")
            continue
        try:
            old_date = date.fromisoformat(t["date"])
        except ValueError:
            skipped.append(f"{_RAIL_EMOJI[rail]} {proj} [orbit:{oid}] "
                           f"(date inválida: {t['date']!r})")
            continue
        new_date = (old_date + timedelta(days=7)).isoformat()
        plan.append((rail, proj, new_date, t["time"]))

    if not plan:
        print("⚠️  No hay bloques clonables de W-1.")
        for s in skipped:
            print(f"   • {s}")
        return 1

    print(f"\n  Voy a clonar {len(plan)} bloque(s) de {prev.name}:")
    by_rail: dict[str, list[tuple[str, str, str]]] = {r: [] for r in _RAILS}
    for rail, proj, d, t in plan:
        by_rail[rail].append((proj, d, t))
    for rail in _RAILS:
        if not by_rail[rail]:
            continue
        print(f"    {_RAIL_EMOJI[rail]} {_RAIL_LABEL[rail]}:")
        for proj, d, t in by_rail[rail]:
            print(f"      • [{proj}] {d} ⏰{t}")
    if skipped:
        print(f"  Skip: {len(skipped)} bloque(s)")
        for s in skipped:
            print(f"    • {s}")

    if not _ask_yn("\n  ¿Crear estos bloques?", default=True):
        return 1

    rails_projects: dict[str, list[str]] = {r: [] for r in _RAILS}
    blocks_by_rail: dict[str, list[tuple[str, str]]] = {r: [] for r in _RAILS}
    for rail, proj, d, t in plan:
        orbit_id = _create_block(proj, rail, week_label, d, t)
        if orbit_id:
            if proj not in rails_projects[rail]:
                rails_projects[rail].append(proj)
            blocks_by_rail[rail].append((proj, orbit_id))
            print(f"  ✓ {_RAIL_EMOJI[rail]} [{proj}] {d} ⏰{t}")

    total = sum(len(v) for v in blocks_by_rail.values())
    if total == 0:
        print("⚠️  No se creó ningún bloque.")
        return 1

    _write_week_file(week_file, target, "normal",
                     rails_projects, blocks_by_rail)
    print(f"\n✓ {total} bloques creados en mission/agenda.md")
    print(f"✓ Archivo semanal: {week_file}")
    return 0


# ── F7: menú sobre semana existente ───────────────────────────────────────

def _load_existing_state(week_file: Path) -> tuple[
        str, dict[str, list[str]], dict[str, list[tuple[str, str]]]]:
    """Read an existing week file → (status, rails_projects, blocks_by_rail)."""
    text = week_file.read_text()
    parsed = _parse_week_file(text)
    detailed = _parse_week_blocks_detailed(text)
    rails_projects: dict[str, list[str]] = {r: [] for r in _RAILS}
    blocks_by_rail: dict[str, list[tuple[str, str]]] = {r: [] for r in _RAILS}
    for rail, proj, oid in detailed:
        if proj not in rails_projects[rail]:
            rails_projects[rail].append(proj)
        blocks_by_rail[rail].append((proj, oid))
    return parsed["status"], rails_projects, blocks_by_rail


def _menu_existing_week(week_file: Path, mission_dir: Path,
                        template: dict, target: date) -> int:
    """Show options when 2026-WNN-focus.md already exists."""
    print(f"⚠️  {week_file.name} ya existe. Opciones:")
    print("  1) regenerar contador (default)")
    print("  2) abrir en $EDITOR")
    print("  3) añadir bloques")
    print("  4) abortar")
    print("  5) escribir retrospectiva")
    try:
        raw = input("  selección [1]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return 1
    choice = raw or "1"

    if choice == "1":
        done, total = _regenerate_counter(week_file, mission_dir)
        print(f"✓ Contador regenerado: {done}/{total} bloques completados.")
        _refresh_year_silent(mission_dir, target.year)
        return 0
    if choice == "2":
        import os
        os.system(f"$EDITOR '{week_file}'")
        return 0
    if choice == "3":
        status, rails_projects, blocks_by_rail = _load_existing_state(week_file)
        rc = _run_mode_libre(mission_dir, template, target, week_file,
                              initial_projects=rails_projects,
                              initial_blocks=blocks_by_rail,
                              initial_status=status)
        if rc == 0:
            _regenerate_counter(week_file, mission_dir)
            _refresh_year_silent(mission_dir, target.year)
        return rc
    if choice == "4":
        return 0
    if choice == "5":
        import os
        editor = os.environ.get("EDITOR", "vi")
        base = os.path.basename(editor.split()[0])
        if base in ("vi", "vim", "nvim"):
            # Posiciona el cursor en la sección Retrospectiva al abrir.
            os.system(f"{editor} '+/^## Retrospectiva' '{week_file}'")
        else:
            print("→ Sección '## Retrospectiva' al final del fichero")
            os.system(f"{editor} '{week_file}'")
        return 0
    print(f"  ⚠️  Selección no válida: {choice!r}")
    return 1


# ── Selector de modo (F5) ─────────────────────────────────────────────────

def _select_mode(mission_dir: Path, target: date) -> Optional[str]:
    """Ask the user which planning mode to use. Returns canonical name or
    None on abort. ``repetir`` only offered when W-1 exists.
    """
    has_prev = _prev_week_file(mission_dir, target) is not None
    options: list[tuple[str, str]] = []
    if has_prev:
        options.append(("repetir", "clona la semana anterior"))
    options.append(("plantilla", "template + W-1 como default de proyectos"))
    options.append(("libre", "prompt proyecto a proyecto"))

    print("Modo:")
    for i, (name, desc) in enumerate(options, 1):
        print(f"  {i}) {name:<10} — {desc}")
    # Default = "repetir" si hay W-1 (path más rápido), "plantilla" si no.
    preferred = "repetir" if has_prev else "plantilla"
    default_idx = next(i for i, (n, _) in enumerate(options, 1) if n == preferred)
    try:
        raw = input(f"  selección [{default_idx}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if not raw:
        return options[default_idx - 1][0]
    if not raw.isdigit() or not (1 <= int(raw) <= len(options)):
        print(f"  ⚠️  Selección no válida")
        return None
    return options[int(raw) - 1][0]
