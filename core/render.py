"""render.py — render .md project files to .html for cloud viewing.

Converts markdown files to standalone HTML with:
  - orbit.css stylesheet
  - KaTeX for LaTeX math rendering
  - Navigation bar with link to index
  - Internal .md links rewritten to .html
"""

import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import markdown

from core.config import ORBIT_HOME, iter_project_dirs, get_type_emojis
from core.deliver import _find_cloud_root, _project_cloud_dir
from core.project import _is_new_project

_CSS_FILENAME = "orbit.css"
_CSS_SOURCE = Path(__file__).parent / "orbit.css"

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{css_path}">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.css">
</head>
<body>
<nav class="orbit-nav">{nav}</nav>
{body}
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.21/dist/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[
    {{left:'$$',right:'$$',display:true}},
    {{left:'$',right:'$',display:false}}
  ]}})"></script>
</body>
</html>"""

_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "sane_lists"]


def _md_to_html(text: str) -> str:
    """Convert markdown text to HTML body."""
    return markdown.markdown(text, extensions=_MD_EXTENSIONS)


def _rewrite_md_links(html: str) -> str:
    """Rewrite .md links to .html in rendered HTML, except inbox.txt."""
    def _replace(m):
        if m.group(1).endswith("inbox"):
            return m.group(0)  # keep inbox.txt as-is
        return f'href="{m.group(1)}.html"'
    return re.sub(r'href="([^"]*?)\.md"', _replace, html)


def _depth(rel_path: Path) -> int:
    """Number of parent directories in a relative path."""
    return len(rel_path.parts) - 1


def _render_file(src: Path, dest: Path, css_rel: str,
                 nav_html: str, title: str = "") -> None:
    """Render a single .md file to .html."""
    text = src.read_text(encoding="utf-8", errors="replace")
    body = _md_to_html(text)
    body = _rewrite_md_links(body)
    if not title:
        # Extract title from first # heading
        m = re.match(r"^#\s+(.+)", text, re.MULTILINE)
        title = m.group(1) if m else src.stem
    html = _HTML_TEMPLATE.format(
        title=title, css_path=css_rel, nav=nav_html, body=body,
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")


# ── Public API ────────────────────────────────────────────────────────────────

def render_project(project_dir: Path, cloud_root: Path) -> int:
    """Render all .md files of a project to HTML in cloud.

    Returns number of files rendered.
    """
    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    if not cloud_dir:
        return 0

    # Collect .md files (root + notes/)
    md_files = list(project_dir.glob("*.md"))
    notes_dir = project_dir / "notes"
    if notes_dir.is_dir():
        md_files.extend(notes_dir.rglob("*.md"))

    # Exclude inbox.txt (lives separately in cloud)
    md_files = [f for f in md_files if f.name != "inbox.txt"]

    rel_project = project_dir.relative_to(ORBIT_HOME)
    rendered = 0
    for src in md_files:
        rel = src.relative_to(project_dir)
        dest = cloud_dir / rel.with_suffix(".html")
        depth = _depth(rel)
        css_rel = ("../" * (depth + 2)) + _CSS_FILENAME
        nav_links = f'<a href="{"../" * (depth + 2)}index.html">🏠 Inicio</a>'
        # Link to project root
        project_html = list(project_dir.glob("*-project.md"))
        if project_html:
            proj_name = project_html[0].stem + ".html"
            if depth > 0:
                proj_name = "../" + proj_name
            nav_links += f' <a href="{proj_name}">📋 Proyecto</a>'
        # Link to project inbox
        inbox_rel = "inbox.txt" if depth == 0 else "../inbox.txt"
        nav_links += f' <a href="{inbox_rel}">📬 Buzón</a>'
        _render_file(src, dest, css_rel, nav_links)
        rendered += 1

    return rendered


def render_all(cloud_root: Optional[Path] = None) -> int:
    """Render all projects to HTML. Returns total files rendered."""
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    # Copy CSS to cloud root
    _sync_css(cloud_root)

    total = 0
    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        n = render_project(project_dir, cloud_root)
        total += n

    return total


def render_changed(cloud_root: Optional[Path] = None) -> int:
    """Render only .md files changed in the last commit. Returns count."""
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    # Copy CSS to cloud root
    _sync_css(cloud_root)

    files = _committed_md_files()
    if not files:
        return 0

    type_emojis = get_type_emojis()
    rendered = 0
    for rel_path in files:
        parts = Path(rel_path).parts
        if len(parts) < 2:
            continue
        if not any(parts[0].startswith(e) for e in type_emojis):
            continue

        src = ORBIT_HOME / rel_path
        if not src.exists():
            continue  # file was deleted

        # Find project dir (2 levels: type_dir/project_dir)
        project_dir = ORBIT_HOME / parts[0] / parts[1]
        if not project_dir.is_dir():
            continue

        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue

        rel_in_project = src.relative_to(project_dir)
        dest = cloud_dir / rel_in_project.with_suffix(".html")
        depth = _depth(rel_in_project)
        css_rel = ("../" * (depth + 2)) + _CSS_FILENAME
        nav_links = f'<a href="{"../" * (depth + 2)}index.html">🏠 Inicio</a>'
        _render_file(src, dest, css_rel, nav_links)
        rendered += 1

    return rendered


def render_index(cloud_root: Optional[Path] = None) -> bool:
    """Generate index.html — clean hub with links to agenda and projects."""
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return False

    from core.config import ORBIT_SPACE, ORBIT_PROMPT

    today = date.today()
    lines = [
        f"# {ORBIT_PROMPT} {ORBIT_SPACE}\n",
        f"*Actualizado: {today.isoformat()}*\n",
        "---\n",
        "## 📋 Navegación\n",
        "- [📅 Agenda — esta semana y la siguiente](agenda.html)",
        "- [📂 Proyectos — estado y enlaces](proyectos.html)",
        "- [📬 Buzón general](inbox.txt) — captura ideas desde el móvil",
        "",
    ]

    md_text = "\n".join(lines)
    body = _md_to_html(md_text)
    body = _rewrite_md_links(body)
    html = _HTML_TEMPLATE.format(
        title=f"{ORBIT_PROMPT} {ORBIT_SPACE}",
        css_path=_CSS_FILENAME,
        nav=f"{ORBIT_PROMPT} {ORBIT_SPACE}",
        body=body,
    )
    (cloud_root / "index.html").write_text(html, encoding="utf-8")
    return True


def render_proyectos(cloud_root: Optional[Path] = None) -> bool:
    """Generate proyectos.html — active projects with status and links."""
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return False

    from core.project import _read_project_meta, _resolve_status
    from core.log import find_proyecto_file, resolve_file

    lines = ["# 📂 Proyectos\n"]

    type_groups: dict = {}
    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        rel = project_dir.relative_to(ORBIT_HOME)
        type_dir = rel.parts[0]
        if type_dir not in type_groups:
            type_groups[type_dir] = []

        meta = _read_project_meta(project_dir)
        status, _, _ = _resolve_status(meta, project_dir)
        project_file = find_proyecto_file(project_dir)

        if project_file:
            html_name = project_file.relative_to(project_dir).with_suffix(".html")
            link = f"{type_dir}/{project_dir.name}/{html_name}"
        else:
            link = f"{type_dir}/{project_dir.name}/"

        # Section links
        sections = []
        for kind, label in [("agenda", "📅"), ("logbook", "📓"),
                            ("highlights", "⭐")]:
            f = resolve_file(project_dir, kind)
            if f.exists():
                f_html = f"{type_dir}/{project_dir.name}/{f.name}".replace(".md", ".html")
                sections.append(f"[{label}]({f_html})")

        from core.tasks import PRIORITY_MAP, normalize
        prio_key = normalize(meta["prioridad"])
        prio_emoji = PRIORITY_MAP.get(prio_key, "")

        _STATUS_EMOJI = {"new": "⬜", "active": "▶️", "paused": "⏸️", "sleeping": "💤"}
        status_emoji = _STATUS_EMOJI.get(status, "❓")

        type_groups[type_dir].append({
            "name": project_dir.name,
            "link": link,
            "status_emoji": status_emoji,
            "prio_emoji": prio_emoji,
            "sections": " ".join(sections),
        })

    for type_dir, projects in sorted(type_groups.items()):
        lines.append(f"\n## {type_dir}\n")
        for p in sorted(projects, key=lambda x: x["name"]):
            lines.append(
                f"- [{p['name']}]({p['link']})  "
                f"{p['status_emoji']} {p['prio_emoji']}  {p['sections']}"
            )

    md_text = "\n".join(lines)
    body = _md_to_html(md_text)
    body = _rewrite_md_links(body)
    nav = '<a href="index.html">🏠 Inicio</a> <a href="agenda.html">📅 Agenda</a>'
    html = _HTML_TEMPLATE.format(
        title="Proyectos", css_path=_CSS_FILENAME, nav=nav, body=body,
    )
    (cloud_root / "proyectos.html").write_text(html, encoding="utf-8")
    return True


def render_agenda(cloud_root: Optional[Path] = None) -> bool:
    """Generate agenda.html — this week + next week across all projects."""
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return False

    from core.agenda_view import _collect_data, _resolve_dirs, _format_by_date

    today = date.today()
    # Monday of this week to Sunday of next week
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=13)

    dirs = _resolve_dirs(None)  # all projects

    lines = [f"# 📅 Agenda\n"]
    lines.append(f"*{start.isoformat()} → {end.isoformat()}*\n")

    # Calendar grid
    cal_lines = _build_calendar_md(dirs, start, end)
    lines.extend(cal_lines)

    collected = _collect_data(dirs, start, end, dated_only=True)
    formatted = _format_by_date(collected, markdown=True, dated_only=True)
    lines.extend(formatted)

    md_text = "\n".join(lines)
    body = _md_to_html(md_text)
    body = _rewrite_md_links(body)
    nav = '<a href="index.html">🏠 Inicio</a> <a href="proyectos.html">📂 Proyectos</a>'
    html = _HTML_TEMPLATE.format(
        title="Agenda", css_path=_CSS_FILENAME, nav=nav, body=body,
    )
    (cloud_root / "agenda.html").write_text(html, encoding="utf-8")
    return True



def ensure_cloud_inboxes(cloud_root: Optional[Path] = None) -> int:
    """Ensure empty inbox.txt files exist in cloud for each project + root.

    Returns number of inbox files created.
    """
    if not cloud_root:
        cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0

    created = 0

    # Global inbox
    inbox = cloud_root / "inbox.txt"
    if not inbox.exists():
        inbox.parent.mkdir(parents=True, exist_ok=True)
        inbox.write_text("")
        created += 1

    # Per-project inboxes
    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue
        inbox = cloud_dir / "inbox.txt"
        if not inbox.exists():
            inbox.parent.mkdir(parents=True, exist_ok=True)
            inbox.write_text("")
            created += 1

    return created


def run_render(project: Optional[str] = None, full: bool = False,
               check: bool = False) -> int:
    """CLI entry point: orbit render [project] [--full] [--check]."""
    if check:
        from core.cloudsync import check_cloud_sync
        return check_cloud_sync()

    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 1

    if project:
        from core.project import _find_new_project
        project_dir = _find_new_project(project)
        if not project_dir:
            return 1
        _sync_css(cloud_root)
        n = render_project(project_dir, cloud_root)
        _render_dashboard(cloud_root)
        print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''} ({project_dir.name})")
    elif full:
        n = render_all(cloud_root)
        _render_dashboard(cloud_root)
        ensure_cloud_inboxes(cloud_root)
        print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''} (todos)")
    else:
        n = render_changed(cloud_root)
        _render_dashboard(cloud_root)
        if n:
            print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''}")
        else:
            print("📄 Sin cambios para renderizar")

    return 0


# ── Calendar ──────────────────────────────────────────────────────────────────

_MONTH_NAMES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def _build_calendar_md(dirs: list, start: date, end: date) -> list:
    """Build a markdown calendar grid for the given period. Returns lines."""
    import calendar as _cal

    from core.agenda_view import _collect_calendar_dates, _project_link

    today = date.today()
    task_dates, event_dates, ms_dates, overdue_dates, overdue_items = \
        _collect_calendar_dates(dirs, start, end)

    lines = []
    if overdue_items:
        lines.append("### ⚠️ Vencidas\n")
        for proj_dir, kind, desc, d_str in sorted(overdue_items, key=lambda x: x[3]):
            display_kind = "☐" if kind == "[ ]" else kind
            proj_tag = _project_link(proj_dir)
            lines.append(f"- {display_kind} {desc} ({d_str}) — {proj_tag}")
        lines.append("")

    def _week_overlaps(week, y, m):
        for day in week:
            if day != 0:
                d = date(y, m, day)
                if start <= d <= end:
                    return True
        return False

    current = date(start.year, start.month, 1)
    while current <= end:
        y, m = current.year, current.month
        cal = _cal.Calendar(firstweekday=0)
        weeks = [w for w in cal.monthdayscalendar(y, m)
                 if _week_overlaps(w, y, m)]

        if weeks:
            lines.append(f"### {_MONTH_NAMES[m]} {y}\n")
            lines.append("| Wk | Lu | Ma | Mi | Ju | Vi | Sa | Do |")
            lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|")

            for week in weeks:
                first_day = next((d for d in week if d != 0), None)
                if first_day is None:
                    continue
                wk_num = date(y, m, first_day).isocalendar()[1]
                cells = [f"**W{wk_num:02d}**"]

                for day in week:
                    if day == 0:
                        cells.append("")
                        continue
                    d = date(y, m, day)
                    in_range = start <= d <= end

                    if not in_range:
                        cells.append(f"~~{day}~~")
                    elif d == today:
                        cells.append(f"**[{day}]**")
                    elif d in overdue_dates:
                        cells.append(f"⚠️{day}")
                    elif d in ms_dates:
                        cells.append(f"🏁{day}")
                    elif d in event_dates:
                        cells.append(f"📅{day}")
                    elif d in task_dates:
                        cells.append(f"✅{day}")
                    else:
                        cells.append(str(day))

                lines.append("| " + " | ".join(cells) + " |")

            lines.append("")

        current = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)

    lines.append("**[N]** hoy · 📅 evento · ✅ tarea · 🏁 hito · ⚠️ vencida")
    lines.append("")
    lines.append("[📆 Abrir Google Calendar](https://calendar.google.com)\n")
    return lines


# ── Helpers ───────────────────────────────────────────────────────────────────

def _render_dashboard(cloud_root: Path) -> None:
    """Render the dashboard pages: index, proyectos, agenda."""
    render_index(cloud_root)
    render_proyectos(cloud_root)
    render_agenda(cloud_root)


def _sync_css(cloud_root: Path) -> None:
    """Copy orbit.css to cloud root if newer or missing."""
    dest = cloud_root / _CSS_FILENAME
    if not dest.exists() or dest.stat().st_mtime < _CSS_SOURCE.stat().st_mtime:
        shutil.copy2(str(_CSS_SOURCE), str(dest))


def _committed_md_files() -> list:
    """Return .md file paths changed in the last commit."""
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            capture_output=True, text=True, cwd=ORBIT_HOME,
        )
        if result.returncode != 0:
            return []
        return [p.strip() for p in result.stdout.splitlines()
                if p.strip().endswith(".md")]
    except FileNotFoundError:
        return []
