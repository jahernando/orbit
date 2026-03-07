"""core/add.py — add items to project sections (ref, result, decision, ring)."""

import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import (
    PROJECTS_DIR, find_project, find_proyecto_file, find_logbook_file,
    format_entry, _append_entry,
)
from core.open import open_file

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
DIARIO_DIR     = MISION_LOG_DIR / "diario"
TEMPLATES_DIR  = Path(__file__).parent.parent / "📐templates"


_REMINDERS_END = "<!-- orbit:reminders:end -->"
_REMINDERS_START = "<!-- orbit:reminders:start -->"


def _copy_ring_to_diary(ring_line: str) -> None:
    """Insert a ring line into today's diary ⏰ Recordatorios section (before end marker)."""
    today = date.today()
    dest  = DIARIO_DIR / f"{today.isoformat()}.md"

    if not dest.exists():
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(tpl.read_text().replace("YYYY-MM-DD", today.isoformat()))

    lines = dest.read_text().splitlines()

    # 1. Insert before the reminders end marker if present
    for i, line in enumerate(lines):
        if line.strip() == _REMINDERS_END:
            lines.insert(i, ring_line)
            dest.write_text("\n".join(lines) + "\n")
            print(f"  → diario {today.isoformat()}: {ring_line}")
            return

    # 2. Section heading exists but no markers — insert after heading
    for i, line in enumerate(lines):
        if line.strip().startswith("## ⏰") and "recordatorio" in line.lower():
            lines[i:i+1] = [
                line,
                _REMINDERS_START,
                ring_line,
                _REMINDERS_END,
            ]
            dest.write_text("\n".join(lines) + "\n")
            print(f"  → diario {today.isoformat()}: {ring_line}")
            return

    # 3. No section at all — inject full block after ## 🎯 Proyecto en foco
    section_block = [
        "",
        "## ⏰ Recordatorios",
        "",
        _REMINDERS_START,
        ring_line,
        _REMINDERS_END,
    ]
    for i, line in enumerate(lines):
        if line.strip().startswith("## 🎯"):
            # find end of this section
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            lines[j:j] = section_block
            dest.write_text("\n".join(lines) + "\n")
            print(f"  → diario {today.isoformat()}: {ring_line}")
            return

    # 4. Last resort: append
    lines += section_block
    dest.write_text("\n".join(lines) + "\n")
    print(f"  → diario {today.isoformat()}: {ring_line}")

# Maps action → (section heading, logbook tag, files subdirectory)
SECTION_MAP = {
    "ref":      ("## 📎 Referencias", "referencia", "references"),
    "result":   ("## 📊 Resultados",  "resultado",  "results"),
    "decision": ("## 📌 Decisiones",  "decision",   "decisions"),
}


def _insert_into_section(proyecto_path: Path, heading: str, new_line: str) -> bool:
    """Insert new_line into the section identified by heading in proyecto.md."""
    lines = proyecto_path.read_text().splitlines()

    section_idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if section_idx is None:
        return False

    # Find where the section ends (next ## heading or EOF)
    end_idx = len(lines)
    for i in range(section_idx + 1, len(lines)):
        if lines[i].startswith("## "):
            end_idx = i
            break

    # Collect section body, drop standalone placeholder '-' and trailing blanks
    body = [l for l in lines[section_idx + 1:end_idx]
            if l.strip() and l.strip() != "-"]
    body.append(new_line)

    rebuilt = lines[:section_idx + 1] + body + [""] + lines[end_idx:]
    proyecto_path.write_text("\n".join(rebuilt) + "\n")
    return True


def _copy_file(file_str: str, dest_dir: Path) -> Optional[Path]:
    src = Path(file_str).expanduser().resolve()
    if not src.exists():
        print(f"Error: fichero no encontrado: {src}")
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return dest


def _git_add(file_path: Path) -> bool:
    result = subprocess.run(
        ["git", "add", "-f", str(file_path)],
        capture_output=True,
        cwd=Path(__file__).parent.parent,
    )
    return result.returncode == 0


def _valid_time(t: str) -> bool:
    parts = t.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


def run_add(
    action: str,
    project: str,
    title: str,
    url: Optional[str],
    file_str: Optional[str],
    sync: bool,
    date_str: Optional[str],
    time_str: Optional[str],
    recur: Optional[str],
    open_after: bool,
    editor: str,
) -> int:
    project_dir = find_project(project)
    if not project_dir:
        return 1

    proyecto_path = find_proyecto_file(project_dir)
    if not proyecto_path or not proyecto_path.exists():
        print(f"Error: fichero de proyecto no encontrado en {project_dir}")
        return 1

    # ── ring ──────────────────────────────────────────────────────────────────
    if action == "ring":
        if not date_str or not time_str:
            print("Error: ring requiere --date y --time")
            return 1
        if not _valid_time(time_str):
            print(f"Error: formato de hora inválido '{time_str}'. Usa HH:MM")
            return 1
        recur_suffix = ""
        if recur:
            tag = recur if recur.startswith("@") else f"@{recur}"
            recur_suffix = f" {tag}"
        new_line = f"- [ ] {date_str} {time_str} {title}{recur_suffix}"
        heading  = "## ⏰ Recordatorios"
        if not _insert_into_section(proyecto_path, heading, new_line):
            print(f"Error: sección '{heading}' no encontrada en {proyecto_path.name}")
            return 1
        print(f"✓ [{project_dir.name}] ⏰ {date_str} {time_str} {title}{recur_suffix}")

        # If today → copy to diary and schedule immediately
        if date_str == date.today().isoformat():
            _copy_ring_to_diary(new_line)
            from core.reminders import _schedule_via_applescript, _mark_scheduled
            h, m = int(time_str[:2]), int(time_str[3:5])
            ok = _schedule_via_applescript(
                title=title, project=project_dir.name,
                year=date.today().year, month=date.today().month, day=date.today().day,
                hour=h, minute=m,
            )
            if ok:
                # find the line just inserted and mark [~]
                all_lines = proyecto_path.read_text().splitlines()
                for idx, l in enumerate(all_lines):
                    if l.strip() == new_line.strip():
                        _mark_scheduled(proyecto_path, idx)
                        break
                print(f"  ⏰ Programado en Reminders.app → {time_str}")
            else:
                print(f"  ⚠️  No se pudo programar en Reminders.app")

        if open_after:
            open_file(proyecto_path, editor)
        return 0

    # ── ref / result / decision ───────────────────────────────────────────────
    heading, tag, dir_name = SECTION_MAP[action]

    # Resolve content and optional file copy
    log_path = None
    if file_str:
        dest_file = _copy_file(file_str, project_dir / dir_name)
        if not dest_file:
            return 1
        rel_path  = f"./{dir_name}/{dest_file.name}"
        content   = f"[{title}]({rel_path})"
        log_path  = rel_path
        if sync:
            if _git_add(dest_file):
                print(f"  ✓ git add -f {dest_file.name}")
            else:
                print(f"  ⚠️  No se pudo añadir a git: {dest_file.name}")
    elif url:
        content  = f"[{title}]({url})"
        log_path = url
    else:
        content = title

    # Insert into project section
    if not _insert_into_section(proyecto_path, heading, f"- {content}"):
        print(f"Error: sección '{heading}' no encontrada en {proyecto_path.name}")
        return 1
    print(f"✓ [{project_dir.name}] {heading}: {content}")

    # Append to logbook
    logbook = find_logbook_file(project_dir)
    if logbook:
        entry = format_entry(title, tag, log_path, None)
        _append_entry(logbook, entry)
        print(f"  → logbook: {entry.strip()}")

    if open_after:
        open_file(proyecto_path, editor)
    return 0
