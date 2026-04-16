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

def _detect_indent_unit(lines: list) -> int:
    """Auto-detect indent unit from the first indented task line.

    Supports 2-space, 4-space, and tab indentation.
    Returns number of characters per indent level (tab counts as 1).
    Defaults to 2 if no indented lines found.
    """
    for line in lines:
        m = _TASK_LINE_RE.match(line)
        if m:
            indent = m.group(1)
            if indent:
                # First indented task line determines the unit
                # Tab = 1 char per level, spaces = count of leading spaces
                if "\t" in indent:
                    return 1
                return len(indent)
    return 2


def _parse_crono_task_line(line: str, indent_unit: int = 2) -> Optional[dict]:
    """Parse a single cronograma task line.

    Format: '- [ ] 1.1 Title | start | duration'
    Returns dict or None if not a task line.
    """
    m = _TASK_LINE_RE.match(line)
    if not m:
        return None
    indent, done_ch, index, rest = m.groups()
    # Normalize: expand tabs to indent_unit spaces for counting
    raw_len = len(indent.replace("\t", " " * indent_unit)) if "\t" in indent else len(indent)
    depth = raw_len // indent_unit if indent_unit > 0 else 0

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

    # Detect indent unit from task lines
    indent_unit = _detect_indent_unit(lines)

    # Parse tasks
    tasks = []
    for i, line in enumerate(lines):
        task = _parse_crono_task_line(line, indent_unit)
        if task:
            task["line_num"] = i + 1  # 1-indexed
            tasks.append(task)
        elif tasks and line.strip() and not line.strip().startswith("#"):
            # Note line: indented text under last task
            raw_indent = line[:len(line) - len(line.lstrip())]
            indent_len = len(raw_indent.replace("\t", " " * indent_unit)) if "\t" in raw_indent else len(raw_indent)
            last = tasks[-1]
            task_indent = last["depth"] * indent_unit
            if indent_len > task_indent:
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

    # Inherit after: from parent — if a parent has after:X and a leaf child
    # has no start_raw, the child inherits the parent's dependency.
    for t in tasks:
        if not _is_leaf(t, parents) and t["start_raw"]:
            parent_start = _resolve_start(t["start_raw"], today)
            if isinstance(parent_start, tuple) and parent_start[0] == "after":
                for child in tasks:
                    if (child["index"].startswith(t["index"] + ".")
                            and _is_leaf(child, parents)
                            and not child["start_raw"]):
                        child["start_raw"] = t["start_raw"]
                        child["_inherited_after"] = True

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
                    # Check if an ancestor has after: (will be inherited at compute time)
                    has_ancestor_after = False
                    idx = t["index"]
                    while "." in idx:
                        idx = idx.rsplit(".", 1)[0]
                        ancestor = by_index.get(idx)
                        if ancestor and ancestor["start_raw"] and _AFTER_RE.match(ancestor["start_raw"]):
                            has_ancestor_after = True
                            break
                    if not has_ancestor_after:
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
    # after: on parents is OK — it gets inherited by leaf children.
    # Only warn about absolute dates or durations on parents (those are ignored).
    for t in tasks:
        if not _is_leaf(t, parents):
            if t["start_raw"] and not _AFTER_RE.match(t["start_raw"]):
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

def _resolve_deadline(metadata: dict, project_dir: Path = None,
                      today: date = None) -> Optional[date]:
    """Resolve deadline from metadata.

    Accepts ISO date ('2026-04-20') or milestone name (looks up in agenda).
    Returns date or None.
    """
    raw = metadata.get("deadline", "")
    if not raw:
        return None
    if today is None:
        today = date.today()

    # Try ISO date
    if _ISO_DATE_RE.match(raw):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None

    # Try milestone name lookup
    if project_dir:
        try:
            from core.agenda_cmds import _read_agenda
            agenda_path = resolve_file(project_dir, "agenda")
            if agenda_path.exists():
                data = _read_agenda(agenda_path)
                for m in data.get("milestones", []):
                    if (raw.lower() in m.get("desc", "").lower()
                            and m.get("date")):
                        try:
                            return date.fromisoformat(m["date"])
                        except ValueError:
                            pass
        except Exception:
            pass

    return None


def _deadline_status(done: int, total: int, deadline: date,
                     today: date = None) -> str:
    """Build a deadline status string with pace warning.

    Returns string like '⚠️ deadline 2026-04-20 (4d) — ritmo: 5/día'
    or '✓ deadline 2026-04-20' if on track or complete.
    """
    if today is None:
        today = date.today()

    remaining = total - done
    days_left = (deadline - today).days

    if remaining == 0:
        return f"✓ deadline {deadline.isoformat()}"

    if days_left < 0:
        return f"⚠️ deadline {deadline.isoformat()} (vencido hace {-days_left}d) — {remaining} pendientes"

    if days_left == 0:
        return f"⚠️ deadline hoy — {remaining} pendientes"

    pace = remaining / days_left
    if pace <= 1:
        icon = "📅"
    elif pace <= 2:
        icon = "⚠️"
    else:
        icon = "⚠️"

    pace_str = f"{pace:.1f}/día" if pace != int(pace) else f"{int(pace)}/día"
    return f"{icon} deadline {deadline.isoformat()} ({days_left}d) — {remaining} pendientes, ritmo: {pace_str}"


def _format_duration(start: date, end: date) -> str:
    """Format duration as human-readable string."""
    if not start or not end:
        return ""
    days = (end - start).days + 1
    if days % 7 == 0:
        return f"{days // 7}W"
    return f"{days}d"


def _format_show(data: dict, today: date = None, project_dir: Path = None) -> str:
    """Format cronograma as a table for terminal display."""
    tasks = data["tasks"]
    name = data["name"]

    if today is None:
        today = date.today()

    if not tasks:
        return f"📊 {name}\n\n(vacío)"

    parents = _parent_indices(tasks)
    dag_only = all(
        t["duration_raw"] is None
        for t in tasks if _is_leaf(t, parents)
    )

    # Deadline
    deadline = _resolve_deadline(data["metadata"], project_dir, today)
    total_leaves = sum(1 for t in tasks if _is_leaf(t, parents))
    done_leaves = sum(1 for t in tasks if _is_leaf(t, parents) and t["done"])

    lines = [f"📊 {name}  {done_leaves}/{total_leaves}"]
    if deadline:
        lines.append(_deadline_status(done_leaves, total_leaves, deadline, today))
    lines.append("")

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


# ── Gantt formatting ────────────────────────────────────────────────────────

# Colorblind-safe palette (no red/green)
_BLUE = "\033[34m"
_YELLOW = "\033[33m"
_GREY = "\033[90m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


def _progress_bar(done: int, total: int, width: int = 30) -> str:
    """Render a progress bar using block chars. Blue=done, grey=remaining."""
    if total == 0:
        return ""
    filled = round(done / total * width)
    bar = f"{_BLUE}{'█' * filled}{_RESET}{_GREY}{'░' * (width - filled)}{_RESET}"
    pct = done * 100 // total
    return f"{bar} {pct}%"


def _format_gantt_dag(data: dict, today: date = None,
                      project_dir: Path = None) -> str:
    """Format DAG-only cronograma as a progress view."""
    tasks = data["tasks"]
    name = data["name"]

    if today is None:
        today = date.today()

    if not tasks:
        return f"📊 {name}\n\n(vacío)"

    parents = _parent_indices(tasks)
    by_index = {t["index"]: t for t in tasks}

    total_all = sum(1 for t in tasks if _is_leaf(t, parents))
    done_all = sum(1 for t in tasks if _is_leaf(t, parents) and t["done"])

    deadline = _resolve_deadline(data["metadata"], project_dir, today)

    lines = [f"{_BOLD}📊 {name}{_RESET}  {done_all}/{total_all}"]
    if deadline:
        lines.append(_deadline_status(done_all, total_all, deadline, today))
    lines.append("")

    for t in tasks:
        indent = "  " * t["depth"]
        is_parent = not _is_leaf(t, parents)

        if is_parent:
            # Count leaves under this parent
            descendants = [d for d in tasks
                           if d["index"].startswith(t["index"] + ".")
                           and _is_leaf(d, parents)]
            d_total = len(descendants)
            d_done = sum(1 for d in descendants if d["done"])
            bar = _progress_bar(d_done, d_total, width=20)
            lines.append(f"{indent}{_BOLD}{t['index']}{_RESET} {t['title']}  {bar}  {d_done}/{d_total}")
        else:
            # Leaf: show checkbox
            if t["done"]:
                mark = f"{_BLUE}[x]{_RESET}"
            else:
                mark = f"{_GREY}[ ]{_RESET}"
            lines.append(f"{indent}{t['index']} {t['title']}  {mark}")

    return "\n".join(lines)


def _format_gantt_dated(data: dict, today: date = None, width: int = 50,
                        project_dir: Path = None) -> str:
    """Format dated cronograma as an ANSI Gantt chart."""
    tasks = data["tasks"]
    name = data["name"]

    if today is None:
        today = date.today()

    if not tasks:
        return f"📊 {name}\n\n(vacío)"

    parents = _parent_indices(tasks)

    # Collect all dates for axis range
    all_dates = []
    for t in tasks:
        if t["start_date"]:
            all_dates.append(t["start_date"])
        if t["end_date"]:
            all_dates.append(t["end_date"])

    if not all_dates:
        return _format_gantt_dag(data)

    min_date = min(all_dates)
    max_date = max(all_dates)
    total_days = (max_date - min_date).days + 1
    if total_days < 1:
        total_days = 1

    def date_to_col(d: date) -> int:
        col = int((d - min_date).days / total_days * width)
        return max(0, min(col, width - 1))

    # Build axis header
    label_width = 40
    axis_line = [" "] * width
    # Mark today
    if min_date <= today <= max_date:
        tc = date_to_col(today)
        axis_line[tc] = "▼"

    # Date labels on axis
    step = max(1, total_days // 5)
    date_labels = " " * label_width + " "
    label_positions = []
    d = min_date
    while d <= max_date:
        col = date_to_col(d)
        label = d.strftime("%m-%d")
        label_positions.append((col, label))
        d += timedelta(days=step)

    # Build label line
    label_line = [" "] * width
    for col, label in label_positions:
        end = min(col + len(label), width)
        for i, ch in enumerate(label):
            if col + i < width:
                label_line[col + i] = ch

    total_leaves = sum(1 for t in tasks if _is_leaf(t, parents))
    done_leaves = sum(1 for t in tasks if _is_leaf(t, parents) and t["done"])

    deadline = _resolve_deadline(data["metadata"], project_dir, today)

    header_lines = [f"{_BOLD}📊 {name}{_RESET}  {done_leaves}/{total_leaves}"]
    if deadline:
        header_lines.append(_deadline_status(done_leaves, total_leaves, deadline, today))

    lines = header_lines + [
        "",
        " " * label_width + " " + "".join(label_line),
        " " * label_width + " " + f"{_YELLOW}{''.join(axis_line)}{_RESET}",
    ]

    for t in tasks:
        is_parent = not _is_leaf(t, parents)
        indent = "  " * t["depth"]
        title = f"{indent}{t['index']} {t['title']}"
        if len(title) > label_width:
            title = title[:label_width - 1] + "…"

        if is_parent:
            # Parent: just show title with counts
            descendants = [d for d in tasks
                           if d["index"].startswith(t["index"] + ".")
                           and _is_leaf(d, parents)]
            d_total = len(descendants)
            d_done = sum(1 for d in descendants if d["done"])
            lines.append(f"{_BOLD}{title:<{label_width}}{_RESET} {d_done}/{d_total}")
        else:
            # Leaf: show bar
            bar = [" "] * width
            if t["start_date"] and t["end_date"]:
                sc = date_to_col(t["start_date"])
                ec = date_to_col(t["end_date"])
                if ec < sc:
                    ec = sc
                # Pick color
                if t["done"]:
                    color = _BLUE
                elif t["end_date"] < today:
                    color = _YELLOW  # overdue
                else:
                    color = _GREY
                for i in range(sc, ec + 1):
                    if i < width:
                        bar[i] = "█"
                bar_str = "".join(bar)
                # Color the filled portion
                bar_str = bar_str.replace("█" * (ec - sc + 1),
                                          f"{color}{'█' * (ec - sc + 1)}{_RESET}", 1)
            else:
                bar_str = "".join(bar)

            status = "[x]" if t["done"] else "[ ]"
            lines.append(f"{title:<{label_width}} {bar_str} {status}")

    return "\n".join(lines)


def _format_gantt(data: dict, today: date = None, mode: str = None,
                  project_dir: Path = None) -> str:
    """Format cronograma as a Gantt chart.

    mode: None (auto-detect), "progress", or "timeline".
    """
    tasks = data["tasks"]
    if not tasks:
        return f"📊 {data['name']}\n\n(vacío)"

    if mode == "progress":
        return _format_gantt_dag(data, today, project_dir)
    if mode == "timeline":
        return _format_gantt_dated(data, today, project_dir=project_dir)

    # Auto-detect
    parents = _parent_indices(tasks)
    dag_only = all(
        t["duration_raw"] is None
        for t in tasks if _is_leaf(t, parents)
    )

    if dag_only:
        return _format_gantt_dag(data, today, project_dir)
    return _format_gantt_dated(data, today, project_dir=project_dir)


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

    print(_format_show(data, project_dir=project_dir))
    return 0


def run_crono_gantt(project: str, name: str, mode: str = None) -> int:
    """Show cronograma as a Gantt chart (progress view or timeline).

    mode: None (auto-detect), "progress", or "timeline".
    """
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

    print(_format_gantt(data, mode=mode, project_dir=project_dir))
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


def run_crono_edit(project: str, name: str, editor: str = "") -> int:
    """Open a cronograma file in the editor."""
    from core.open import open_file

    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    return open_file(path, editor)


def _reindex_lines(lines: list) -> tuple:
    """Reindex task lines based on position and depth.

    Returns (new_lines, rename_map) where rename_map is {old_index: new_index}.
    Preserves non-task lines as-is. Updates after: references.
    """
    indent_unit = _detect_indent_unit(lines)
    # First pass: parse tasks and compute new indices
    counters = {}  # depth -> current counter
    rename_map = {}  # old_index -> new_index
    task_infos = []  # (line_idx, old_index, new_index)

    for i, line in enumerate(lines):
        task = _parse_crono_task_line(line, indent_unit)
        if not task:
            continue
        depth = task["depth"]

        # Reset deeper counters
        for d in list(counters.keys()):
            if d > depth:
                del counters[d]

        # Increment counter at this depth
        counters[depth] = counters.get(depth, 0) + 1

        # Build new index from parent chain
        parts = []
        for d in range(depth + 1):
            parts.append(str(counters.get(d, 1)))
        new_index = ".".join(parts)

        rename_map[task["index"]] = new_index
        task_infos.append((i, task["index"], new_index))

    # Sort renames by length descending to avoid partial replacements
    # (e.g. replacing "1.3" before "1.3.2" would corrupt "after:1.3.2")
    sorted_renames = sorted(rename_map.items(), key=lambda x: len(x[0]), reverse=True)

    # Second pass: rewrite lines with new indices and updated after: references
    new_lines = list(lines)
    for line_idx, old_idx, new_idx in task_infos:
        line = new_lines[line_idx]
        m = _TASK_LINE_RE.match(line)
        if m:
            indent, done_ch, _old, rest = m.groups()
            # Update after: references in rest (longest first)
            for old_ref, new_ref in sorted_renames:
                rest = rest.replace(f"after:{old_ref}", f"after:{new_ref}")
            new_lines[line_idx] = f"{indent}- [{done_ch}] {new_idx} {rest}"

    return new_lines, rename_map


def run_crono_reindex(project: str, name: str) -> int:
    """Reindex a cronograma — renumber all task indices sequentially."""
    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    lines = path.read_text(encoding="utf-8").splitlines()
    new_lines, rename_map = _reindex_lines(lines)

    # Count actual changes
    changes = sum(1 for old, new in rename_map.items() if old != new)
    if changes == 0:
        print(f"✓ [{project_dir.name}] {path.name}: índices ya correctos")
        return 0

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    for old, new in rename_map.items():
        if old != new:
            print(f"  {old} → {new}")
    print(f"\n✓ [{project_dir.name}] {changes} índice(s) renumerado(s)")
    return 0


def run_crono_done(project: str, name: str, index: str = None) -> int:
    """Mark a cronograma task as done.

    If index is None, show interactive selection of pending tasks.
    If index matches partially (by index or title), disambiguate.
    """
    import sys

    project_dir = _find_new_project(project)
    if not project_dir:
        print(f"Proyecto no encontrado: {project}")
        return 1

    path = _find_crono_file(project_dir, name)
    if not path:
        print(f"Cronograma no encontrado: {name}")
        return 1

    data = _parse_crono_file(path)
    parents = _parent_indices(data["tasks"])
    pending = [t for t in data["tasks"]
               if not t["done"] and _is_leaf(t, parents)]

    if not pending:
        print(f"✓ [{project_dir.name}] Todas las tareas completadas")
        return 0

    # Resolve which task to mark done
    target = None
    if index:
        # Try exact index match first
        exact = [t for t in pending if t["index"] == index]
        if exact:
            target = exact[0]
        else:
            # Partial match on index or title
            matches = [t for t in pending
                       if index.lower() in t["index"].lower()
                       or index.lower() in t["title"].lower()]
            if len(matches) == 1:
                target = matches[0]
            elif len(matches) > 1:
                target = _pick_crono_task(matches)
            else:
                print(f"No se encontró '{index}' entre las tareas pendientes")
                return 1
    else:
        # Interactive selection
        target = _pick_crono_task(pending)

    if not target:
        return 1

    # Mark done in file
    lines = path.read_text(encoding="utf-8").splitlines()
    indent_unit = _detect_indent_unit(lines)
    for i, line in enumerate(lines):
        task = _parse_crono_task_line(line, indent_unit)
        if task and task["index"] == target["index"]:
            lines[i] = line.replace("- [ ]", "- [x]", 1)
            print(f"✓ [{project_dir.name}] completada: {target['index']} {target['title']}")
            break

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Log to logbook
    crono_name = _parse_crono_file(path)["name"]
    _log_crono_done(project_dir, crono_name, target["index"], target["title"])
    return 0


def _pick_crono_task(tasks: list) -> Optional[dict]:
    """Interactive selection from a list of cronograma tasks."""
    import sys

    print(f"\nTareas pendientes:")
    for i, t in enumerate(tasks, 1):
        indent = "  " * t["depth"]
        print(f"  {i}. {indent}{t['index']} {t['title']}")
    print()

    if not sys.stdin.isatty():
        return None

    try:
        raw = input("Selecciona (número, índice o texto): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw:
        return None

    # Try as number
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(tasks):
            return tasks[idx]
        print(f"Fuera de rango (1–{len(tasks)})")
        return None

    # Try as index or text match
    matches = [t for t in tasks
               if raw.lower() in t["index"].lower()
               or raw.lower() in t["title"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Múltiples coincidencias para '{raw}':")
        for j, t in enumerate(matches, 1):
            print(f"  {j}. {t['index']} {t['title']}")
        try:
            raw2 = input("Selecciona (#): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw2.isdigit():
            idx = int(raw2) - 1
            if 0 <= idx < len(matches):
                return matches[idx]
        print("Cancelado.")
        return None

    print(f"Sin coincidencias para '{raw}'")
    return None


def _log_crono_done(project_dir: Path, crono_name: str,
                    index: str, title: str) -> None:
    """Log a cronograma task completion to the project's logbook."""
    try:
        from core.log import resolve_file, _append_entry, format_entry
        logbook_path = resolve_file(project_dir, "logbook")
        msg = f"[📊{crono_name}] {index} {title}"
        entry = format_entry(msg, "apunte", None, None)
        _append_entry(logbook_path, entry)
    except Exception:
        pass  # never crash on logging


def detect_crono_completions() -> list:
    """Detect cronograma tasks completed manually (via git diff).

    Compares staged+unstaged changes in crono files. Returns list of
    (project_dir, crono_name, index, title) for newly completed tasks.
    """
    import subprocess
    from core.config import iter_project_dirs
    from core.project import _is_new_project

    results = []
    dirs = [d for d in iter_project_dirs() if _is_new_project(d)]

    for project_dir in dirs:
        cronos_dir = project_dir / _CRONO_DIR
        if not cronos_dir.exists():
            continue
        for crono_file in cronos_dir.glob("crono-*.md"):
            try:
                # Get diff for this file (staged + unstaged)
                diff = subprocess.run(
                    ["git", "diff", "HEAD", "--", str(crono_file)],
                    capture_output=True, text=True, cwd=project_dir,
                    timeout=5,
                )
                if diff.returncode != 0 or not diff.stdout:
                    continue

                # Parse diff: look for lines that changed from [ ] to [x]
                data = _parse_crono_file(crono_file)
                crono_name = data["name"]
                indent_unit = _detect_indent_unit(
                    crono_file.read_text().splitlines())

                for line in diff.stdout.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        task = _parse_crono_task_line(line[1:], indent_unit)
                        if task and task["done"]:
                            # Check the removed line had [ ]
                            results.append((
                                project_dir, crono_name,
                                task["index"], task["title"]
                            ))
            except Exception:
                continue

    return results


def log_crono_completions() -> int:
    """Detect and log manually completed crono tasks. Called from commit."""
    completions = detect_crono_completions()
    for project_dir, crono_name, index, title in completions:
        _log_crono_done(project_dir, crono_name, index, title)
    return len(completions)


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
