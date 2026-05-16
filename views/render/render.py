"""render.py — render .md project files to .html for cloud viewing.

Converts markdown files to standalone HTML with:
  - orbit.css stylesheet
  - KaTeX for LaTeX math rendering
  - Navigation bar with link to index
  - Internal .md links rewritten to .html
"""

import json
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta
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
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  document.querySelectorAll('pre code.language-mermaid').forEach(el => {{
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    el.parentElement.replaceWith(div);
  }});
  mermaid.initialize({{ startOnLoad: false, securityLevel: 'loose' }});
  await mermaid.run();
</script>
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
                 nav_html: str, title: str = "",
                 extra_md: str = "") -> None:
    """Render a single .md file to .html. ``extra_md`` is appended to
    the source markdown before conversion (used to surface tracked
    files in the rendered project page)."""
    text = src.read_text(encoding="utf-8", errors="replace")
    if extra_md:
        text = text + "\n\n" + extra_md
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

def _workspace_cache_dir(project_dir: Path) -> Optional[Path]:
    """Return the per-workspace cache dir for tracked-note mirrors.

    The cache lives at ``<workspace>/.cache/notes/<project_basename>/``.
    Walks parents from ``project_dir`` looking for the workspace root
    (the dir that already contains ``.cache`` or, failing that, the
    nearest ``$HOME/<emoji>orbit-*`` ancestor). Returns None if the
    workspace can't be located.
    """
    home = Path.home()
    for ancestor in [project_dir] + list(project_dir.parents):
        if ancestor == home or ancestor == ancestor.parent:
            return None
        parent = ancestor.parent
        if parent == home and ancestor.name.startswith(("🚀", "🌿", "🛠️", "📦")):
            return ancestor / ".cache" / "notes" / project_dir.name
    return None


def _resolve_external(project_dir: Path, name: str, source_path: str) -> Optional[Path]:
    """Return a Path with current content of the externa, or None if
    both source and cache are unavailable.

    Source path wins; if missing, fall back to last-known cache. The
    cache is refreshed lazily here (when source is reachable and newer).
    """
    src = Path(source_path)
    cache_dir = _workspace_cache_dir(project_dir)
    cache_file = cache_dir / name if cache_dir else None

    if src.exists() and src.is_file():
        if cache_file is not None:
            try:
                src_mtime = src.stat().st_mtime
                cache_mtime = cache_file.stat().st_mtime if cache_file.exists() else -1
                if src_mtime > cache_mtime:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, cache_file)
            except OSError:
                pass
        return src

    # Source missing — fall back to cache.
    if cache_file is not None and cache_file.exists():
        return cache_file
    return None


def render_project(project_dir: Path, cloud_root: Path) -> int:
    """Render all .md files of a project to HTML in cloud.

    Returns number of files rendered.

    Externas (tracked) are rendered from their resolved source path
    (or from the local mtime-cache if source is unreachable).
    """
    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    if not cloud_dir:
        return 0

    from core.tracked import load_registry
    tracked_registry = load_registry(project_dir)   # {filename: source_path}

    notes_dir = project_dir / "notes"

    # Collect .md files: root + propias under notes/ (excluding externas, handled separately).
    md_files = list(project_dir.glob("*.md"))
    if notes_dir.is_dir():
        for p in notes_dir.iterdir():
            if not p.name.endswith(".md"):
                continue
            if p.name in tracked_registry:
                continue   # externa, handled below
            if p.is_file() and not p.is_symlink():
                md_files.append(p)

    # Exclude inbox.txt (lives separately in cloud)
    md_files = [f for f in md_files if f.name != "inbox.txt"]

    # Build the "Tracked" snippet for the project.md page.
    tracked_section_md = ""
    if tracked_registry:
        lines = ["## 🔄 Tracked"]
        for name, src_path in sorted(tracked_registry.items()):
            note_html = f"notes/{name}".replace(".md", ".html")
            display_name = Path(name).stem
            lines.append(f"- [{display_name}](./{note_html}) → `{src_path}`")
        tracked_section_md = "\n".join(lines)

    rendered = 0
    broken_externas = []
    for src in md_files:
        rel = src.relative_to(project_dir)
        dest = cloud_dir / rel.with_suffix(".html")
        depth = _depth(rel)
        css_rel = ("../" * (depth + 2)) + _CSS_FILENAME
        nav_links = f'<a href="{"../" * (depth + 2)}index.html">🏠 Inicio</a>'
        project_html = list(project_dir.glob("*-project.md"))
        if project_html:
            proj_name = project_html[0].stem + ".html"
            if depth > 0:
                proj_name = "../" + proj_name
            nav_links += f' <a href="{proj_name}">📋 Proyecto</a>'
        extra = tracked_section_md if src.name.endswith("-project.md") else ""
        _render_file(src, dest, css_rel, nav_links, extra_md=extra)
        rendered += 1

    # Render externas: read content from the resolved source (or cache),
    # write HTML into cloud_dir/notes/<name>.html.
    for name, src_path in tracked_registry.items():
        content_src = _resolve_external(project_dir, name, src_path)
        if content_src is None:
            broken_externas.append(name)
            continue
        rel = Path("notes") / name
        dest = cloud_dir / rel.with_suffix(".html")
        depth = _depth(rel)
        css_rel = ("../" * (depth + 2)) + _CSS_FILENAME
        nav_links = f'<a href="{"../" * (depth + 2)}index.html">🏠 Inicio</a>'
        project_html = list(project_dir.glob("*-project.md"))
        if project_html:
            proj_name = project_html[0].stem + ".html"
            if depth > 0:
                proj_name = "../" + proj_name
            nav_links += f' <a href="{proj_name}">📋 Proyecto</a>'
        _render_file(content_src, dest, css_rel, nav_links)
        rendered += 1

    if broken_externas:
        print(f"  ⚠️  [{project_dir.name}] tracked sin fuente accesible: "
              f"{', '.join(broken_externas)}")

    return rendered


def render_delivered_md(project_dir: Path, dest_md: Path,
                        cloud_root: Path) -> bool:
    """Render a .md file delivered into cloud/ to its sibling .html.

    dest_md must live under cloud_root/{type}/{project}/cloud/…/file.md
    (as produced by deliver_file). Writes file.html next to it with
    css/nav links pointing back to the cloud root.
    """
    if dest_md.suffix.lower() != ".md":
        return False
    cloud_dir = _project_cloud_dir(project_dir, cloud_root)
    if not cloud_dir:
        return False
    try:
        rel = dest_md.relative_to(cloud_dir)
    except ValueError:
        return False

    _sync_css(cloud_root)
    dest_html = dest_md.with_suffix(".html")
    depth = _depth(rel)
    css_rel = ("../" * (depth + 2)) + _CSS_FILENAME
    nav_links = f'<a href="{"../" * (depth + 2)}index.html">🏠 Inicio</a>'
    project_html = list(project_dir.glob("*-project.md"))
    if project_html:
        proj_name = project_html[0].stem + ".html"
        if depth > 0:
            proj_name = ("../" * depth) + proj_name
        nav_links += f' <a href="{proj_name}">📋 Proyecto</a>'
    _render_file(dest_md, dest_html, css_rel, nav_links)
    return True


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


# ── Post-save action: emit ICS ───────────────────────────────────────────────
#
# Acción independiente del render: vive en commit_post (no anidada en
# after_render). Render escribe HTML a `cloud_root/{type}/{proj}/`; ICS
# escribe a `cloud_root/calendar/`. Directorios disjuntos, sin coupling.
# `orbit render` manual NO la dispara — usa `orbit ics --workspace`.

def _action_ics_emit_workspace(ctx):
    """Best-effort: regenerate .ics files + trigger Calendar.app reload.

    Resuelve cloud_root vía _find_cloud_root() si no viene en ctx (caso
    de commit_post, donde el chain no propaga cloud_root). Failures no
    bloquean el chain — print warning + return ok=False (non-critical).
    """
    cloud_root = (ctx or {}).get("cloud_root") if isinstance(ctx, dict) else None
    if cloud_root is None:
        cloud_root = _find_cloud_root()
    if cloud_root is None:
        return {"ok": True, "msg": "no cloud_root", "data": None}
    try:
        from views.cal.ics import write_workspace
        write_workspace(cloud_root)
        return {"ok": True, "msg": "emitted"}
    except Exception as exc:
        print(f"  ⚠️  ics: error generando calendarios: {exc}")
        return {"ok": False, "msg": f"{type(exc).__name__}: {exc}"}


# Chain composition and bindings live in core/hooks_catalog.json — loaded once
# by hooks.bootstrap() at orbit startup.
from core import hooks as _hooks


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


_SECRETARY_DIRNAME = "📋secretary"


def render_workspace_dashboard(cloud_root: Optional[Path] = None) -> int:
    """Render workspace.md + 📋secretary/*.md a HTML en cloud_root.

    Fuente única de la verdad-derivada: los .md ya los generó secretary
    (panel, agenda-next, calendar, projects) en `📋secretary/`. Aquí
    sólo los proyectamos a HTML para el cloud.

    - workspace.md         → cloud_root/index.html   (front-page del cloud)
    - 📋secretary/*.md     → cloud_root/📋secretary/*.html

    Returns el número de ficheros renderizados.
    """
    if cloud_root is None:
        cloud_root = _find_cloud_root()
    if cloud_root is None:
        return 0

    _sync_css(cloud_root)
    rendered = 0

    # workspace.md → index.html (front-page).
    ws_src = ORBIT_HOME / "workspace.md"
    if ws_src.exists():
        _render_file(ws_src, cloud_root / "index.html",
                     css_rel=_CSS_FILENAME, nav_html="")
        rendered += 1

    # 📋secretary/*.md → 📋secretary/*.html.
    sec_src_dir = ORBIT_HOME / _SECRETARY_DIRNAME
    if sec_src_dir.is_dir():
        sec_cloud_dir = cloud_root / _SECRETARY_DIRNAME
        sec_cloud_dir.mkdir(parents=True, exist_ok=True)
        nav = '<a href="../index.html">🏠 Inicio</a>'
        css_rel = "../" + _CSS_FILENAME
        for md in sorted(sec_src_dir.glob("*.md")):
            dest = sec_cloud_dir / md.with_suffix(".html").name
            _render_file(md, dest, css_rel=css_rel, nav_html=nav)
            rendered += 1

    return rendered



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
    """CLI entry point: orbit render [project] [--full] [--check].

    Sólo HTML — los .ics ya no se regeneran automáticamente desde aquí
    (desde 2026-05-16 fase C: ics es post-action propia de save).
    Para refrescar los .ics manualmente: `orbit ics --workspace`.
    """
    if check:
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
        render_workspace_dashboard(cloud_root)
        print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''} ({project_dir.name})")
    elif full:
        n = render_all(cloud_root)
        render_workspace_dashboard(cloud_root)
        print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''} (todos)")
    else:
        n = render_changed(cloud_root)
        render_workspace_dashboard(cloud_root)
        if n:
            print(f"📄 {n} fichero{'s' if n != 1 else ''} renderizado{'s' if n != 1 else ''}")
        else:
            print("📄 Sin cambios para renderizar")

    if not check:
        print("ℹ️  .ics no regenerados — `orbit ics --workspace` si los necesitas.")

    return 0


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Render-to-cloud workflow ─────────────────────────────────────────────────
#
# Funciones que orquestan el flujo completo "render → cloud_root":
# render_changed/render_all + dashboard + escritura de status. Antes vivían
# en core/cloudsync.py con el nombre "sync_*"; el nombre era engañoso porque
# no sincronizan con el cliente cloud (OneDrive/Drive lo hace solo cuando
# detecta cambios en cloud_root). Movidas aquí en 2026-05-16 (fase B).

def render_changed_to_cloud() -> int:
    """Render .md cambiados al cloud + dashboard + write status.

    Llamada por el hook `render_to_cloud` tras cada save y
    por `cmd_render` desde el CLI. Devuelve número de ficheros rendered.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        _write_sync_status(0, error="cloud_root no encontrado")
        return 0
    try:
        n = render_changed(cloud_root)
        render_workspace_dashboard(cloud_root)
        _write_sync_status(n)
        return n
    except Exception as e:
        _write_sync_status(0, error=str(e))
        raise


def render_changed_to_cloud_background() -> None:
    """Lanza render_changed_to_cloud en un subprocess (fire & forget)."""
    import os
    import sys
    from core.config import ORBIT_CODE
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ORBIT_CODE) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = (
        "try:\n"
        "    from views.render.render import render_changed_to_cloud\n"
        "    render_changed_to_cloud()\n"
        "except Exception as e:\n"
        "    from views.render.render import _write_sync_status\n"
        "    _write_sync_status(0, error=str(e))\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", cmd],
        cwd=str(ORBIT_HOME),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )


def render_all_to_cloud(dry_run: bool = False) -> int:
    """Render todos los proyectos al cloud + dashboard. Sin status write."""
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 0
    n = render_all(cloud_root)
    render_workspace_dashboard(cloud_root)
    return n


def _action_render_to_cloud(ctx):
    """Post-action de save: lanza render→cloud en subprocess.

    Antes era `_action_cloudsync_push_background` en core/commit.py,
    luego `_action_render_changed_background` (2026-05-16 fase B).
    Renombrado a `render_to_cloud` 2026-05-16 para alinear con la
    matriz de viewers (secretary/render/ics/ring son building blocks
    reutilizables con nombres simétricos).
    """
    try:
        render_changed_to_cloud_background()
        print("  ☁️  Render al cloud en background.")
        return {"ok": True, "msg": "launched"}
    except Exception as e:
        return {"ok": False, "msg": f"{type(e).__name__}: {e}"}


# ── Sync status (last render result) ─────────────────────────────────────────
#
# Antes vivía en core/cloudsync.py (separación heredada de cuando había
# un "cloud sync" real con AppleScript). En 2026-05-16 se fundió aquí
# porque todo lo que hacía era escribir/leer el resultado del último
# render. Naming actualizado: cloud_sync_status_check → render_status_check.

_SYNC_STATUS_FILE = ORBIT_HOME / ".cloud-sync.json"


def _write_sync_status(rendered: int, error: str = "") -> None:
    """Write sync result to .cloud-sync.json for startup verification."""
    commit = ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=ORBIT_HOME,
        )
        if r.returncode == 0:
            commit = r.stdout.strip()
    except FileNotFoundError:
        pass

    status = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "commit": commit,
        "rendered": rendered,
        "ok": not error,
    }
    if error:
        status["error"] = error
    try:
        _SYNC_STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False))
    except OSError:
        pass


def _read_sync_status() -> dict:
    """Read last sync status. Returns {} if not available."""
    try:
        return json.loads(_SYNC_STATUS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def startup_render_status_check() -> None:
    """Check last background render status and warn if it failed."""
    status = _read_sync_status()
    if not status:
        return
    if status.get("ok"):
        return
    error = status.get("error", "desconocido")
    commit = status.get("commit", "?")
    time = status.get("time", "?")
    print(f"  ⚠️  El último render al cloud falló ({time}, commit {commit})")
    print(f"      Error: {error}")
    print(f"      Ejecuta 'render --full' para re-sincronizar.")
    print()


def check_cloud_sync() -> int:
    """Compare source .md mtimes vs cloud .html — report stale files.

    Returns 0 if all up to date, 1 if stale files found.
    """
    cloud_root = _find_cloud_root()
    if not cloud_root:
        return 1

    stale = []
    missing = []
    ok = 0

    for project_dir in iter_project_dirs():
        if not _is_new_project(project_dir):
            continue
        cloud_dir = _project_cloud_dir(project_dir, cloud_root)
        if not cloud_dir:
            continue

        md_files = list(project_dir.glob("*.md"))
        notes_dir = project_dir / "notes"
        if notes_dir.is_dir():
            md_files.extend(notes_dir.rglob("*.md"))

        for src in md_files:
            rel = src.relative_to(project_dir)
            dest = cloud_dir / rel.with_suffix(".html")
            if not dest.exists():
                missing.append((project_dir.name, rel))
            elif dest.stat().st_mtime < src.stat().st_mtime:
                stale.append((project_dir.name, rel))
            else:
                ok += 1

    # Show last sync status
    status = _read_sync_status()
    if status:
        flag = "✓" if status.get("ok") else "✗"
        print(f"  Último sync: {flag} {status.get('time', '?')} "
              f"(commit {status.get('commit', '?')}, "
              f"{status.get('rendered', 0)} renderizados)")

    if not stale and not missing:
        print(f"  ☁️  Cloud al día — {ok} ficheros OK")
        return 0

    if stale:
        print(f"\n  ⚠️  {len(stale)} fichero{'s' if len(stale) != 1 else ''} desactualizado{'s' if len(stale) != 1 else ''}:")
        for proj, rel in stale[:10]:
            print(f"      {proj}/{rel}")
        if len(stale) > 10:
            print(f"      ... y {len(stale) - 10} más")

    if missing:
        print(f"\n  ❌ {len(missing)} fichero{'s' if len(missing) != 1 else ''} sin HTML en cloud:")
        for proj, rel in missing[:10]:
            print(f"      {proj}/{rel}")
        if len(missing) > 10:
            print(f"      ... y {len(missing) - 10} más")

    print(f"\n  Ejecuta 'render --full' para re-sincronizar.")
    return 1


def _action_render_status_check(ctx):
    """Read .cloud-sync.json, warn si el último render al cloud falló.

    Heredero de `cloud_sync_status_check` (vivía en core/shell.py + helper
    en core/cloudsync.py). Renombrado y movido a views/render/ en
    2026-05-16 porque el "sync" que reportaba era el render: nada que
    ver con cloud-sync genérico, simplemente el último resultado del
    subprocess de render lanzado por commit_post.
    """
    startup_render_status_check()
    return {"ok": True}
