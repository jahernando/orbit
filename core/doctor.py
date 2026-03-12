"""doctor.py — validate syntax of project files (logbook, agenda, highlights).

  orbit doctor [project]         # check all or one project
  orbit doctor --fix [project]   # check and offer to fix

Also runs automatically on shell startup to catch issues early.
"""

import re
from datetime import date
from pathlib import Path
from typing import Optional

from core.log import PROJECTS_DIR, TAG_EMOJI, VALID_TYPES, resolve_file
from core.project import _find_new_project, _is_new_project
from core.agenda_cmds import (
    _parse_task_line, _parse_event_line,
    _TASK_HEADER, _MS_HEADER, _EV_HEADER, VALID_RECUR, is_valid_recur,
)
from core.highlights import SECTION_MAP


# ── Issue dataclass ───────────────────────────────────────────────────────────

class Issue:
    __slots__ = ("project", "file", "line_num", "line", "msg", "fix")

    def __init__(self, project: str, file: str, line_num: int,
                 line: str, msg: str, fix: Optional[str] = None):
        self.project  = project
        self.file     = file
        self.line_num = line_num
        self.line     = line
        self.msg      = msg
        self.fix      = fix   # suggested fixed line, or None

    def __repr__(self):
        return f"[{self.project}] {self.file}:{self.line_num} — {self.msg}"


# ── Logbook validation ────────────────────────────────────────────────────────

_DATE_RE     = re.compile(r"^(\d{4}-\d{2}-\d{2})\s")
_TAG_RE      = re.compile(r"#(\w+)")
_EMOJI_BY_TAG = TAG_EMOJI
_TAG_BY_EMOJI = {v: k for k, v in TAG_EMOJI.items()}

# Emojis that can appear at position after the date
_ALL_ENTRY_EMOJIS = set(TAG_EMOJI.values())


def _check_logbook(project_name: str, path: Path,
                   max_lines: int = 200) -> list:
    """Validate logbook entries. Only checks last max_lines lines."""
    if not path.exists():
        return []

    issues = []
    lines = path.read_text().splitlines()

    # Only check last N lines for performance
    start = max(0, len(lines) - max_lines)
    last_was_entry = False
    in_comment = False

    for i in range(start, len(lines)):
        line = lines[i]
        s = line.strip()

        # Skip HTML comment blocks (single-line and multi-line)
        if in_comment:
            if "-->" in s:
                in_comment = False
            last_was_entry = False
            continue
        if "<!--" in s:
            if "-->" not in s:
                in_comment = True
            last_was_entry = False
            continue

        # Skip headers, blank lines
        if not s or s.startswith("#"):
            last_was_entry = False
            continue

        # Indented continuation line (2+ spaces or tab) — valid multiline
        if (line.startswith("  ") or line.startswith("\t") or line.startswith("\u200b")) and last_was_entry:
            continue

        # Should be a dated entry
        dm = _DATE_RE.match(s)
        if not dm:
            # Non-date, non-indented line after an entry → suggest indenting
            if last_was_entry:
                fixed = f"  {line}"
                issues.append(Issue(project_name, path.name, i + 1, line,
                                    "Línea suelta en logbook — ¿continuación? (indentar con 2 espacios)",
                                    fix=fixed))
            # Line that looks like a broken entry
            elif s.startswith("20") or any(s.startswith(e) for e in _ALL_ENTRY_EMOJIS):
                issues.append(Issue(project_name, path.name, i + 1, line,
                                    "Fecha mal formada"))
            last_was_entry = False
            continue

        last_was_entry = True
        date_str = dm.group(1)

        # Validate date
        try:
            date.fromisoformat(date_str)
        except ValueError:
            issues.append(Issue(project_name, path.name, i + 1, line,
                                f"Fecha inválida: {date_str}"))
            continue

        # Check for type tag
        tags = _TAG_RE.findall(s)
        entry_tags = [t for t in tags if t in VALID_TYPES]

        if not entry_tags:
            issues.append(Issue(project_name, path.name, i + 1, line,
                                "Falta #tipo (idea, apunte, referencia, etc.)"))
            continue

        tipo = entry_tags[0]
        expected_emoji = _EMOJI_BY_TAG.get(tipo, "")

        if expected_emoji:
            after_date = s[len(date_str):].lstrip()

            # Check if emoji is missing entirely
            has_any_emoji = any(after_date.startswith(e) for e in _ALL_ENTRY_EMOJIS)
            if not has_any_emoji:
                fixed = f"{date_str} {expected_emoji} {after_date}"
                issues.append(Issue(project_name, path.name, i + 1, line,
                                    f"Falta emoji para #{tipo} (esperado {expected_emoji})",
                                    fix=fixed))
            else:
                # Check if a wrong emoji is present
                for emoji in _ALL_ENTRY_EMOJIS:
                    if after_date.startswith(emoji) and emoji != expected_emoji:
                        fixed = f"{date_str} {expected_emoji} {after_date[len(emoji):].lstrip()}"
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            f"Emoji {emoji} no coincide con #{tipo} (esperado {expected_emoji})",
                                            fix=fixed))
                        break

    return issues


# ── Agenda validation ─────────────────────────────────────────────────────────

def _check_agenda(project_name: str, path: Path) -> list:
    """Validate agenda.md: tasks, milestones, events."""
    if not path.exists():
        return []

    issues = []
    lines = path.read_text().splitlines()
    section = None  # "tasks", "milestones", "events", or None
    in_comment = False

    # Regex for non-zero-padded dates in parentheses, e.g. (2026-3-28) or (2026-03-1)
    _LOOSE_DATE_RE = re.compile(r"\((\d{4})-(\d{1,2})-(\d{1,2})\)")

    for i, line in enumerate(lines):
        s = line.strip()

        # Skip HTML comment blocks (single-line and multi-line)
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if "<!--" in s:
            if "-->" not in s:
                in_comment = True
            continue

        # Detect section
        if s == _TASK_HEADER:
            section = "tasks"
            continue
        elif s == _MS_HEADER:
            section = "milestones"
            continue
        elif s == _EV_HEADER:
            section = "events"
            continue
        elif s.startswith("## "):
            section = None
            continue

        if not s or s.startswith("#"):
            continue

        if section in ("tasks", "milestones"):
            # Check for non-zero-padded dates like (2026-3-28)
            loose_m = _LOOSE_DATE_RE.search(s)
            if loose_m:
                y, m_str, d_str = loose_m.group(1), loose_m.group(2), loose_m.group(3)
                if len(m_str) < 2 or len(d_str) < 2:
                    fixed_date = f"({y}-{int(m_str):02d}-{int(d_str):02d})"
                    fixed_line = s[:loose_m.start()] + fixed_date + s[loose_m.end():]
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        f"Fecha sin zero-padding: {loose_m.group(0)} → {fixed_date}",
                                        fix=fixed_line))

            # Should be a task/milestone line
            if s.startswith("- "):
                parsed = _parse_task_line(s)
                if parsed is None:
                    # Check common issues
                    if re.match(r"^- \[.\]", s):
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            "Marcador inválido (usar [ ], [x] o [-])"))
                    else:
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            "Línea no reconocida en sección de tareas/hitos"))
                else:
                    # Validate date if present
                    if parsed["date"]:
                        try:
                            date.fromisoformat(parsed["date"])
                        except ValueError:
                            issues.append(Issue(project_name, path.name, i + 1, line,
                                                f"Fecha inválida: {parsed['date']}"))
                    # Validate recurrence
                    if parsed.get("recur") and not is_valid_recur(parsed["recur"]):
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            f"Recurrencia inválida: {parsed['recur']}"))
                    # Validate until date
                    if parsed.get("until"):
                        try:
                            date.fromisoformat(parsed["until"])
                        except ValueError:
                            issues.append(Issue(project_name, path.name, i + 1, line,
                                                f"Fecha until inválida: {parsed['until']}"))
                    # Empty description
                    if not parsed["desc"]:
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            "Tarea/hito sin descripción"))

        elif section == "events":
            parsed = _parse_event_line(s)
            if parsed is None:
                # Check if it looks like a malformed event
                if re.match(r"^\d{4}-\d{2}-\d{2}", s):
                    if " — " not in s and (" - " in s or " – " in s):
                        # Wrong dash type
                        fixed = re.sub(r"\s+[-–]\s+", " — ", s, count=1)
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            "Usar em-dash (—) en vez de guión",
                                            fix=fixed))
                    else:
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            "Evento mal formado (esperado: YYYY-MM-DD — descripción)"))
                elif s.startswith("- "):
                    # Task-style line in events section
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        "Línea con formato de tarea en sección de eventos"))
            else:
                # Validate dates
                try:
                    date.fromisoformat(parsed["date"])
                except ValueError:
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        f"Fecha de evento inválida: {parsed['date']}"))
                if parsed.get("end"):
                    try:
                        date.fromisoformat(parsed["end"])
                    except ValueError:
                        issues.append(Issue(project_name, path.name, i + 1, line,
                                            f"Fecha end inválida: {parsed['end']}"))
                if not parsed["desc"]:
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        "Evento sin descripción"))

    return issues


# ── Highlights validation ─────────────────────────────────────────────────────

_VALID_HEADINGS = set(SECTION_MAP.values())


def _check_highlights(project_name: str, path: Path) -> list:
    """Validate highlights.md sections and items."""
    if not path.exists():
        return []

    issues = []
    lines = path.read_text().splitlines()
    in_section = False
    in_comment = False

    for i, line in enumerate(lines):
        s = line.strip()

        if not s:
            continue

        # Skip HTML comment blocks (single-line and multi-line)
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if "<!--" in s:
            if "-->" not in s or s.index("-->") < s.index("<!--"):
                in_comment = True
            continue

        if s.startswith("## "):
            if s in _VALID_HEADINGS:
                in_section = True
            elif s.startswith("# "):
                in_section = s.startswith("## ")
            else:
                issues.append(Issue(project_name, path.name, i + 1, line,
                                    f"Sección no reconocida: {s}"))
                in_section = True  # still parse items
            continue

        if s.startswith("# "):
            in_section = False
            continue

        if in_section:
            if not s.startswith("- "):
                issues.append(Issue(project_name, path.name, i + 1, line,
                                    "Entrada debe empezar con '- '"))
                continue
            # Check for malformed markdown links
            if "[" in s and "]" in s:
                # Should have matching brackets and parens
                if s.count("[") != s.count("]"):
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        "Corchetes desbalanceados en link"))
                elif "](" in s and s.count("(") != s.count(")"):
                    issues.append(Issue(project_name, path.name, i + 1, line,
                                        "Paréntesis desbalanceados en link"))

    return issues


# ── Main check function ──────────────────────────────────────────────────────

def check_project(project_dir: Path, max_logbook_lines: int = 200) -> list:
    """Run all checks on a single project. Returns list of Issues."""
    name = project_dir.name
    issues = []

    logbook = resolve_file(project_dir, "logbook")
    issues.extend(_check_logbook(name, logbook, max_logbook_lines))

    agenda = resolve_file(project_dir, "agenda")
    issues.extend(_check_agenda(name, agenda))

    highlights = resolve_file(project_dir, "highlights")
    issues.extend(_check_highlights(name, highlights))

    return issues


def check_all_projects(max_logbook_lines: int = 200) -> list:
    """Run checks on all new-format projects."""
    if not PROJECTS_DIR.exists():
        return []
    issues = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        if d.is_dir() and _is_new_project(d):
            issues.extend(check_project(d, max_logbook_lines))
    return issues


# ── Apply fixes ───────────────────────────────────────────────────────────────

def _apply_fix(issue: Issue) -> bool:
    """Apply a single fix by replacing the line in the file."""
    if not issue.fix:
        return False
    path = PROJECTS_DIR
    # Find the actual file
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and d.name == issue.project:
            path = d
            break
    else:
        return False

    file_path = path / issue.file
    if not file_path.exists():
        return False

    lines = file_path.read_text().splitlines()
    idx = issue.line_num - 1
    if idx < 0 or idx >= len(lines):
        return False

    from core.undo import save_snapshot
    save_snapshot(file_path)
    lines[idx] = issue.fix
    file_path.write_text("\n".join(lines) + "\n")
    return True


# ── CLI command ───────────────────────────────────────────────────────────────

def run_doctor(project: Optional[str] = None, fix: bool = False) -> int:
    """Run doctor checks and optionally fix issues."""
    import sys

    if project:
        project_dir = _find_new_project(project)
        if project_dir is None:
            return 1
        issues = check_project(project_dir)
    else:
        issues = check_all_projects()

    if not issues:
        print("✓ Todo en orden — no se encontraron problemas.")
        return 0

    print(f"  🏥 {len(issues)} problema{'s' if len(issues) != 1 else ''} encontrado{'s' if len(issues) != 1 else ''}:")
    print()

    fixable   = [i for i in issues if i.fix]
    unfixable = [i for i in issues if not i.fix]

    for issue in issues:
        prefix = "  🔧" if issue.fix else "  ⚠️"
        print(f"{prefix} [{issue.project}] {issue.file}:{issue.line_num}")
        print(f"      {issue.msg}")
        if issue.fix:
            print(f"      → {issue.fix}")
        print()

    if fix and fixable and sys.stdin.isatty():
        print(f"  {len(fixable)} correcciones disponibles:")
        _interactive_fix(fixable)

    if unfixable:
        print(f"  {len(unfixable)} problema{'s' if len(unfixable) != 1 else ''} requiere{'n' if len(unfixable) != 1 else ''} corrección manual.")

    return 0


def _interactive_fix(fixable: list) -> None:
    """Interactively apply fixes, same pattern as untracked files."""
    import sys

    while True:
        for i, issue in enumerate(fixable, 1):
            print(f"      [{i}] {issue.file}:{issue.line_num} — {issue.msg}")
            print(f"          → {issue.fix}")

        try:
            prompt = "  ¿Corregir? [S=todos / 1,2,... / n]: " if len(fixable) > 1 else "  ¿Corregir? [S/n]: "
            ans = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if ans.lower() in ("n", "no"):
            return

        if ans == "" or ans.lower() in ("s", "si", "sí", "y", "yes"):
            selected = fixable
        else:
            try:
                indices = [int(x.strip()) for x in ans.split(",")]
                selected = [fixable[i - 1] for i in indices if 1 <= i <= len(fixable)]
            except (ValueError, IndexError):
                print("  ⚠️  Selección no válida")
                continue
            if not selected:
                print("  ⚠️  Ninguna corrección seleccionada")
                continue

        # Confirm if partial selection
        if len(selected) < len(fixable):
            print(f"\n  Correcciones seleccionadas:")
            for issue in selected:
                print(f"      {issue.file}:{issue.line_num} → {issue.fix}")
            try:
                confirm = input("  ¿Confirmar? [S/n/r(repetir)]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if confirm in ("r", "repetir"):
                print()
                continue
            if confirm not in ("", "s", "si", "sí", "y", "yes"):
                return

        applied = 0
        for issue in selected:
            if _apply_fix(issue):
                applied += 1

        print(f"  ✓ {applied} corrección{'es' if applied != 1 else ''} aplicada{'s' if applied != 1 else ''}")
        return


# ── Background check for startup ─────────────────────────────────────────────

def doctor_background():
    """Run doctor in a background thread. Returns (thread, results_holder).

    results_holder is a list that will contain the issues when done.
    """
    import threading

    results = []

    def _do_check():
        try:
            issues = check_all_projects()
            results.extend(issues)
        except Exception:
            pass

    t = threading.Thread(target=_do_check, daemon=True)
    t.start()
    return t, results
