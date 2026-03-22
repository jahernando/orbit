"""cronograma.py — nested task schedules with dependencies and duration.

  crono add <project> <name>       # create cronograma file + register in agenda
  crono show <project> <name>      # table with computed dates
  crono check <project> <name>     # doctor validation
  crono list <project>             # list project cronogramas
  crono done <project> <name> <idx> # mark task as done
"""

import re
from collections import deque
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.log import resolve_file
from core.project import _find_new_project

# ── Constants ────────────────────────────────────────────────────────────────

_CRONO_HEADER = "## 📊 Cronogramas"
_CRONO_DIR = "cronos"

_INDEX_RE = re.compile(r"^(\d+(?:\.\d+)*)$")
_DUR_RE = re.compile(r"^(\d+)([dW])$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
_ISO_WEEK_DAY_RE = re.compile(r"^(\d{4})-W(\d{2})-(mon|tue|wed|thu|fri|sat|sun)$")
_AFTER_RE = re.compile(r"^after:(.+)$")

_DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_TASK_LINE_RE = re.compile(
    r"^(\s*)- \[([ x])\]\s+"   # indent + checkbox
    r"(\d+(?:\.\d+)*)\s+"      # index
    r"(.+)$"                    # rest: title | start | duration
)

_META_RE = re.compile(r"^(\w[\w-]*):\s*(.+)$")


# ── Parsing ──────────────────────────────────────────────────────────────────

def _parse_crono_task_line(line: str) -> Optional[dict]:
    """Parse a single cronograma task line.

    Format: '- [ ] 1.1 Title | start | duration'
    Returns dict or None if not a task line.
    """
    m = _TASK_LINE_RE.match(line)
    if not m:
        return None
    indent, done_ch, index, rest = m.groups()
    depth = len(indent) // 2  # 2-space indent per level

    parts = [p.strip() for p in rest.split("|")]
    title = parts[0]
    start_raw = parts[1] if len(parts) > 1 and parts[1] else None
    duration_raw = parts[2] if len(parts) > 2 and parts[2] else None

    return {
        "index": index,
        "title": title,
        "done": done_ch == "x",
        "start_raw": start_raw,
        "duration_raw": duration_raw,
        "depth": depth,
        "notes": [],
        "children": [],
        "start_date": None,
        "end_date": None,
    }


def _parse_metadata(lines: list) -> dict:
    """Parse metadata lines at the top of a cronograma file.

    Metadata lines are 'key: value' after the '# Cronograma:' header,
    before the first task line.
    """
    meta = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _META_RE.match(stripped)
        if m:
            key, val = m.group(1), m.group(2).strip()
            meta[key] = val
        else:
            break  # first non-metadata, non-blank, non-header line
    return meta


def _parse_excludes(meta: dict) -> set:
    """Parse 'exclude' metadata into a set of excluded items.

    Returns a set of:
    - weekday ints (0=mon..6=sun)
    - date objects (specific dates)
    - (year, week) tuples (ISO weeks)
    """
    raw = meta.get("exclude", "")
    if not raw:
        return set()

    excludes = set()
    for token in [t.strip() for t in raw.split(",")]:
        if not token:
            continue
        # Weekday
        if token.lower() in _DAY_MAP:
            excludes.add(_DAY_MAP[token.lower()])
            continue
        # ISO week
        wm = _ISO_WEEK_RE.match(token)
        if wm:
            excludes.add((int(wm.group(1)), int(wm.group(2))))
            continue
        # ISO date
        if _ISO_DATE_RE.match(token):
            try:
                excludes.add(date.fromisoformat(token))
            except ValueError:
                pass
            continue
    return excludes


def _is_excluded(d: date, excludes: set) -> bool:
    """Check if a date falls on an excluded day."""
    if not excludes:
        return False
    # Weekday check (int 0-6)
    if d.weekday() in excludes:
        return True
    # Specific date check
    if d in excludes:
        return True
    # ISO week check
    iso = d.isocalendar()
    if (iso[0], iso[1]) in excludes:
        return True
    return False


def _parse_crono_file(path: Path) -> dict:
    """Parse a cronograma .md file.

    Returns: {name, metadata, tasks, lines}
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Extract name from header
    name = path.stem.removeprefix("crono-")
    for line in lines:
        if line.startswith("# Cronograma:"):
            name = line.split(":", 1)[1].strip()
            break

    # Parse metadata (lines between header and first task)
    meta_lines = []
    past_header = False
    for line in lines:
        if line.startswith("# "):
            past_header = True
            continue
        if past_header:
            if _TASK_LINE_RE.match(line):
                break
            meta_lines.append(line)

    metadata = _parse_metadata(meta_lines)

    # Parse tasks
    tasks = []
    for i, line in enumerate(lines):
        task = _parse_crono_task_line(line)
        if task:
            task["line_num"] = i + 1  # 1-indexed
            tasks.append(task)
        elif tasks and line.strip() and not line.strip().startswith("#"):
            # Note line: indented text under last task
            indent = len(line) - len(line.lstrip())
            last = tasks[-1]
            task_indent = last["depth"] * 2
            if indent > task_indent:
                last["notes"].append(line.strip())

    return {"name": name, "metadata": metadata, "tasks": tasks, "lines": lines}


def _build_tree(tasks: list) -> list:
    """Build parent-child hierarchy from flat task list using index depth.

    Sets 'children' on parent tasks. Returns root-level tasks.
    """
    # Map index to task
    by_index = {t["index"]: t for t in tasks}

    for t in tasks:
        t["children"] = []

    roots = []
    for t in tasks:
        idx = t["index"]
        parts = idx.rsplit(".", 1)
        if len(parts) == 1:
            # Root-level task
            roots.append(t)
        else:
            parent_idx = parts[0]
            parent = by_index.get(parent_idx)
            if parent:
                parent["children"].append(t)
            else:
                roots.append(t)  # orphan becomes root

    return roots


def _parent_indices(tasks: list) -> set:
    """Return set of indices that have children (i.e. are parents)."""
    all_indices = {t["index"] for t in tasks}
    parents = set()
    for t in tasks:
        if "." in t["index"]:
            parent_idx = t["index"].rsplit(".", 1)[0]
            if parent_idx in all_indices:
                parents.add(parent_idx)
    return parents


def _is_leaf(task: dict, parents: set) -> bool:
    """Check if task is a leaf (not in the parents set). O(1)."""
    return task["index"] not in parents


# ── Date computation ─────────────────────────────────────────────────────────

def _resolve_start(raw: str, today: date = None) -> object:
    """Convert raw start string to a date or after-marker.

    Returns:
    - date object for absolute dates
    - ('after', index_str) tuple for dependencies
    - None if raw is None/empty
    """
    if not raw:
        return None
    if today is None:
        today = date.today()

    raw = raw.strip()

    # after:X
    am = _AFTER_RE.match(raw)
    if am:
        return ("after", am.group(1))

    # ISO date
    if _ISO_DATE_RE.match(raw):
        return date.fromisoformat(raw)

    # ISO week + day
    wdm = _ISO_WEEK_DAY_RE.match(raw)
    if wdm:
        year, week, day_name = int(wdm.group(1)), int(wdm.group(2)), wdm.group(3)
        day_num = _DAY_MAP[day_name]
        # Monday of that week
        jan4 = date(year, 1, 4)
        start_of_w1 = jan4 - timedelta(days=jan4.weekday())
        monday = start_of_w1 + timedelta(weeks=week - 1)
        return monday + timedelta(days=day_num)

    # ISO week (= Monday)
    wm = _ISO_WEEK_RE.match(raw)
    if wm:
        year, week = int(wm.group(1)), int(wm.group(2))
        jan4 = date(year, 1, 4)
        start_of_w1 = jan4 - timedelta(days=jan4.weekday())
        return start_of_w1 + timedelta(weeks=week - 1)

    return None


def _parse_duration(raw: str) -> Optional[int]:
    """Parse duration string to number of calendar days.

    '5d' → 5, '2W' → 14. Returns None if invalid.
    """
    if not raw:
        return None
    m = _DUR_RE.match(raw.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if n < 1:
        return None
    return n if unit == "d" else n * 7


def _add_working_days(start: date, days: int, excludes: set) -> date:
    """Compute end date by adding N working days, skipping excluded days.

    days=1 means the task occupies 1 day → end = start (if start not excluded).
    Returns the end date (inclusive).
    """
    if not excludes:
        return start + timedelta(days=days - 1)

    current = start
    counted = 0
    limit = days * 10  # safety: max 10x expansion from excludes
    for _ in range(limit):
        if not _is_excluded(current, excludes):
            counted += 1
            if counted == days:
                return current
        current += timedelta(days=1)
    return current  # fallback if excludes are too aggressive


def _compute_dates(tasks: list, metadata: dict = None, today: date = None):
    """Resolve dependencies and compute start/end dates for all tasks.

    Modifies tasks in place. Handles DAG-only mode (no durations).
    """
    if today is None:
        today = date.today()
    if metadata is None:
        metadata = {}

    by_index = {t["index"]: t for t in tasks}
    parents = _parent_indices(tasks)
    excludes = _parse_excludes(metadata)
    initial_time_raw = metadata.get("initial-time", "today")
    if initial_time_raw == "today":
        initial_time = today
    else:
        resolved = _resolve_start(initial_time_raw, today)
        initial_time = resolved if isinstance(resolved, date) else today

    # Check if this is DAG-only mode (no leaf has duration)
    dag_only = all(
        t["duration_raw"] is None
        for t in tasks if _is_leaf(t, parents)
    )

    # Build dependency graph for topological sort
    # deps[idx] = set of indices this task depends on (via after:)
    deps = {}
    for t in tasks:
        t_deps = set()
        start = _resolve_start(t["start_raw"], today)
        if isinstance(start, tuple) and start[0] == "after":
            t_deps.add(start[1])
        deps[t["index"]] = t_deps

    # Topological sort (Kahn's algorithm)
    order = _topo_sort_indices(tasks, deps)

    # Compute dates in topological order (leaves first concept, but topo handles it)
    for idx in order:
        t = by_index[idx]
        leaf = _is_leaf(t, parents)

        if leaf:
            # Resolve start
            start = _resolve_start(t["start_raw"], today)
            if isinstance(start, tuple) and start[0] == "after":
                dep_task = by_index.get(start[1])
                if dep_task and dep_task["end_date"]:
                    s = dep_task["end_date"] + timedelta(days=1)
                    # Skip excluded days for start
                    while _is_excluded(s, excludes):
                        s += timedelta(days=1)
                    t["start_date"] = s
                else:
                    t["start_date"] = None
            elif isinstance(start, date):
                t["start_date"] = start
            elif not t["start_raw"]:
                # No start declared — use initial-time for root tasks
                parent_idx = t["index"].rsplit(".", 1)[0] if "." in t["index"] else None
                if parent_idx is None or parent_idx not in by_index:
                    t["start_date"] = initial_time
                else:
                    t["start_date"] = None  # will be set if parent resolves

            # Compute end
            if not dag_only and t["start_date"]:
                dur = _parse_duration(t["duration_raw"])
                if dur:
                    t["end_date"] = _add_working_days(t["start_date"], dur, excludes)
        else:
            # Parent task: start/end from all descendants
            desc = [by_index[c["index"]] for c in tasks
                    if c["index"].startswith(t["index"] + ".")]

            child_starts = [d["start_date"] for d in desc if d["start_date"]]
            child_ends = [d["end_date"] for d in desc if d["end_date"]]

            t["start_date"] = min(child_starts) if child_starts else None
            t["end_date"] = max(child_ends) if child_ends else None


def _topo_sort_indices(tasks: list, deps: dict) -> list:
    """Topological sort of task indices. Returns ordered list of indices.

    Raises ValueError if cycle detected.
    """
    all_indices = [t["index"] for t in tasks]
    parents = _parent_indices(tasks)
    in_degree = {idx: 0 for idx in all_indices}
    reverse = {idx: [] for idx in all_indices}

    for idx, idx_deps in deps.items():
        for dep in idx_deps:
            if dep in in_degree:
                in_degree[idx] += 1
                reverse[dep].append(idx)

    # Parent depends on all direct children (for date aggregation)
    for t in tasks:
        if not _is_leaf(t, parents):
            child_indices = [
                c["index"] for c in tasks
                if c["index"].startswith(t["index"] + ".")
                and c["index"].count(".") == t["index"].count(".") + 1
            ]
            for ci in child_indices:
                if ci in in_degree:
                    in_degree[t["index"]] += 1
                    reverse[ci].append(t["index"])

    queue = deque(idx for idx, deg in in_degree.items() if deg == 0)
    order = []

    while queue:
        idx = queue.popleft()
        order.append(idx)
        for neighbor in reverse[idx]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(all_indices):
        # Cycle detected — find which indices are in the cycle
        remaining = set(all_indices) - set(order)
        raise ValueError(f"Ciclo en dependencias: {', '.join(sorted(remaining))}")

    return order


# ── Validation (Doctor) ──────────────────────────────────────────────────────

def _check_cronograma(project_name: str, path: Path) -> list:
    """Validate a cronograma file. Returns list of Issue objects."""
    from core.doctor import Issue

    issues = []
    fname = path.name

    try:
        data = _parse_crono_file(path)
    except Exception as e:
        issues.append(Issue(project_name, fname, 0, "", f"Error al parsear: {e}"))
        return issues

    tasks = data["tasks"]
    if not tasks:
        return issues

    by_index = {t["index"]: t for t in tasks}
    parents = _parent_indices(tasks)

    # Rule 1: Unique indices
    seen_indices = {}
    for t in tasks:
        if t["index"] in seen_indices:
            issues.append(Issue(
                project_name, fname, t["line_num"], "",
                f"Índice duplicado: {t['index']} (ya en línea {seen_indices[t['index']]})"
            ))
        else:
            seen_indices[t["index"]] = t["line_num"]

    # Rule 2: Dependencies exist
    for t in tasks:
        if t["start_raw"]:
            am = _AFTER_RE.match(t["start_raw"])
            if am:
                dep_idx = am.group(1)
                if dep_idx not in by_index:
                    issues.append(Issue(
                        project_name, fname, t["line_num"], "",
                        f"Dependencia inexistente: after:{dep_idx}"
                    ))

    # Rule 3: No cycles
    deps = {}
    for t in tasks:
        t_deps = set()
        if t["start_raw"]:
            am = _AFTER_RE.match(t["start_raw"])
            if am and am.group(1) in by_index:
                t_deps.add(am.group(1))
        deps[t["index"]] = t_deps

    try:
        _topo_sort_indices(tasks, deps)
    except ValueError as e:
        issues.append(Issue(project_name, fname, 0, "", str(e)))

    # Check DAG-only mode
    dag_only = all(
        t["duration_raw"] is None
        for t in tasks if _is_leaf(t, parents)
    )

    # Rules 4-5: Leaf tasks need start and duration (unless DAG-only)
    if not dag_only:
        for t in tasks:
            if _is_leaf(t, parents):
                if not t["start_raw"]:
                    # Check if it would get initial-time
                    parent_idx = t["index"].rsplit(".", 1)[0] if "." in t["index"] else None
                    if parent_idx and parent_idx in by_index:
                        issues.append(Issue(
                            project_name, fname, t["line_num"], "",
                            f"Tarea hoja sin inicio: {t['index']} {t['title']}"
                        ))
                if not t["duration_raw"]:
                    issues.append(Issue(
                        project_name, fname, t["line_num"], "",
                        f"Tarea hoja sin duración: {t['index']} {t['title']}"
                    ))

    # Rule 6: Parent with explicit start/duration (warning)
    for t in tasks:
        if not _is_leaf(t, parents):
            if t["start_raw"]:
                issues.append(Issue(
                    project_name, fname, t["line_num"], "",
                    f"⚠️ Tarea padre con inicio explícito (se ignora): {t['index']}"
                ))
            if t["duration_raw"]:
                issues.append(Issue(
                    project_name, fname, t["line_num"], "",
                    f"⚠️ Tarea padre con duración explícita (se ignora): {t['index']}"
                ))

    # Rule 7: Valid date formats
    for t in tasks:
        if t["start_raw"] and not _AFTER_RE.match(t["start_raw"]):
            raw = t["start_raw"]
            if not (_ISO_DATE_RE.match(raw) or _ISO_WEEK_RE.match(raw)
                    or _ISO_WEEK_DAY_RE.match(raw)):
                issues.append(Issue(
                    project_name, fname, t["line_num"], "",
                    f"Formato de fecha inválido: {raw}"
                ))
            elif _ISO_DATE_RE.match(raw):
                try:
                    date.fromisoformat(raw)
                except ValueError:
                    issues.append(Issue(
                        project_name, fname, t["line_num"], "",
                        f"Fecha inválida: {raw}"
                    ))

    # Rule 8: Valid duration formats
    for t in tasks:
        if t["duration_raw"]:
            if not _DUR_RE.match(t["duration_raw"]):
                issues.append(Issue(
                    project_name, fname, t["line_num"], "",
                    f"Formato de duración inválido: {t['duration_raw']}"
                ))
            else:
                n = int(_DUR_RE.match(t["duration_raw"]).group(1))
                if n < 1:
                    issues.append(Issue(
                        project_name, fname, t["line_num"], "",
                        f"Duración debe ser ≥ 1: {t['duration_raw']}"
                    ))

    return issues


# ── Show formatting ──────────────────────────────────────────────────────────

def _format_duration(start: date, end: date) -> str:
    """Format duration as human-readable string."""
    if not start or not end:
        return ""
    days = (end - start).days + 1
    if days % 7 == 0:
        return f"{days // 7}W"
    return f"{days}d"


def _format_show(data: dict, today: date = None) -> str:
    """Format cronograma as a table for terminal display."""
    tasks = data["tasks"]
    name = data["name"]

    if not tasks:
        return f"📊 {name}\n\n(vacío)"

    parents = _parent_indices(tasks)
    dag_only = all(
        t["duration_raw"] is None
        for t in tasks if _is_leaf(t, parents)
    )

    lines = [f"📊 {name}", ""]

    if dag_only:
        # DAG-only: show structure without dates
        hdr = f"{'Idx':<8} {'Estado':<8} {'Tarea'}"
        lines.append(hdr)
        lines.append("─" * len(hdr))
        for t in tasks:
            indent = "  " * t["depth"]
            status = "[x]" if t["done"] else "[ ]"
            lines.append(f"{t['index']:<8} {status:<8} {indent}{t['title']}")
    else:
        # Full table with dates
        hdr = (f"{'Idx':<8} {'Estado':<8} {'Tarea':<40} "
               f"{'Inicio':<12} {'Fin':<12} {'Dur':<6}")
        lines.append(hdr)
        lines.append("─" * len(hdr))
        if today is None:
            today = date.today()
        for t in tasks:
            indent = "  " * t["depth"]
            status = "[x]" if t["done"] else "[ ]"
            title = f"{indent}{t['title']}"
            s = t["start_date"].isoformat() if t["start_date"] else "—"
            e = t["end_date"].isoformat() if t["end_date"] else "—"
            dur = _format_duration(t["start_date"], t["end_date"])

            # ANSI colors
            prefix = ""
            suffix = ""
            if t["done"]:
                prefix = "\033[32m"  # green
                suffix = "\033[0m"
            elif t["end_date"] and t["end_date"] < today and not t["done"]:
                prefix = "\033[31m"  # red (overdue)
                suffix = "\033[0m"

            line = f"{t['index']:<8} {status:<8} {title:<40} {s:<12} {e:<12} {dur:<6}"
            lines.append(f"{prefix}{line}{suffix}")

    return "\n".join(lines)


# ── Commands ─────────────────────────────────────────────────────────────────

def run_crono_add(project: str, name: str) -> int:
    """Create a new cronograma file and register it in agenda.md."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    cronos_dir = project_dir / _CRONO_DIR
    cronos_dir.mkdir(exist_ok=True)

    slug = name.lower().replace(" ", "-")
    crono_path = cronos_dir / f"crono-{slug}.md"

    if crono_path.exists():
        print(f"Ya existe: {crono_path.name}")
        return 1

    # Write template
    template = (
        f"# Cronograma: {name}\n"
        f"\n"
        f"- [ ] 1 {name}\n"
        f"  - [ ] 1.1 Primera tarea | {date.today().isoformat()} | 1W\n"
    )
    crono_path.write_text(template, encoding="utf-8")

    # Register in agenda.md
    _ensure_crono_section(project_dir)
    agenda_path = resolve_file(project_dir, "agenda")
    text = agenda_path.read_text(encoding="utf-8")
    link_line = f"- [{name}]({_CRONO_DIR}/crono-{slug}.md)"

    # Insert after section header
    lines = text.splitlines()
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip() == _CRONO_HEADER:
            insert_idx = i + 1
            # Skip any existing links
            while insert_idx < len(lines) and lines[insert_idx].startswith("- ["):
                insert_idx += 1
            break

    if insert_idx is not None:
        lines.insert(insert_idx, link_line)
        agenda_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"✓ [{project_dir.name}] cronograma creado: {crono_path.name}")
    return 0


def _ensure_crono_section(project_dir: Path):
    """Ensure ## 📊 Cronogramas section exists in agenda.md."""
    agenda_path = resolve_file(project_dir, "agenda")
    if not agenda_path.exists():
        return

    text = agenda_path.read_text(encoding="utf-8")
    if _CRONO_HEADER in text:
        return

    # Append section at the end
    if not text.endswith("\n"):
        text += "\n"
    text += f"\n{_CRONO_HEADER}\n"
    agenda_path.write_text(text, encoding="utf-8")


def run_crono_show(project: str, name: str) -> int:
    """Show cronograma with computed dates."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    data = _parse_crono_file(path)
    if data["tasks"]:
        _compute_dates(data["tasks"], data["metadata"])

    print(_format_show(data))
    return 0


def run_crono_check(project: str, name: str) -> int:
    """Run doctor validation on a cronograma."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    issues = _check_cronograma(project_dir.name, path)
    if not issues:
        print(f"✓ [{project_dir.name}] {path.name}: sin problemas")
        return 0

    for issue in issues:
        print(issue)
    print(f"\n{len(issues)} problema(s) encontrado(s)")
    return 1


def run_crono_list(project: str) -> int:
    """List cronogramas in a project."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    cronos_dir = project_dir / _CRONO_DIR
    if not cronos_dir.exists():
        print(f"[{project_dir.name}] No hay cronogramas")
        return 0

    files = sorted(cronos_dir.glob("crono-*.md"))
    if not files:
        print(f"[{project_dir.name}] No hay cronogramas")
        return 0

    print(f"📊 Cronogramas de {project_dir.name}\n")
    for f in files:
        data = _parse_crono_file(f)
        total = len(data["tasks"])
        done = sum(1 for t in data["tasks"] if t["done"])
        print(f"  {data['name']}  ({done}/{total} completadas)")

    return 0


def run_crono_done(project: str, name: str, index: str) -> int:
    """Mark a cronograma task as done."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        task = _parse_crono_task_line(line)
        if task and task["index"] == index:
            if task["done"]:
                print(f"Ya completada: {index} {task['title']}")
                return 0
            # Replace [ ] with [x]
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            found = True
            print(f"✓ [{project_dir.name}] completada: {index} {task['title']}")
            break

    if not found:
        print(f"Tarea no encontrada: {index}")
        return 1

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def _find_crono_file(project_dir: Path, name: str) -> Optional[Path]:
    """Find a cronograma file by exact or partial name match."""
    cronos_dir = project_dir / _CRONO_DIR
    if not cronos_dir.exists():
        return None

    slug = name.lower().replace(" ", "-")

    # Exact match
    exact = cronos_dir / f"crono-{slug}.md"
    if exact.exists():
        return exact

    # Partial match
    candidates = list(cronos_dir.glob("crono-*.md"))
    matches = [f for f in candidates if slug in f.stem.lower()]
    if len(matches) == 1:
        return matches[0]

    return None
