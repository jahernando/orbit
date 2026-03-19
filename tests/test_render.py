"""test_render.py — tests for MD→HTML rendering and cloud sync."""

import pytest
from pathlib import Path
from datetime import date

from core.render import (
    _md_to_html, _rewrite_md_links, render_project, render_all,
    render_index, render_proyectos, render_agenda,
    ensure_cloud_inboxes, _sync_css,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cloud_env(tmp_path, monkeypatch):
    """Isolated environment with workspace + cloud root."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cloud = tmp_path / "cloud"
    cloud.mkdir()

    # orbit.json with cloud_root
    import json
    (workspace / "orbit.json").write_text(json.dumps({
        "space": "test-ws",
        "emoji": "🚀",
        "cloud_root": str(cloud),
        "types": {"software": "💻", "gestion": "⚙️"},
    }))

    monkeypatch.setattr("core.config.ORBIT_HOME", workspace)
    monkeypatch.setattr("core.config._ORBIT_JSON_PATH", workspace / "orbit.json")
    monkeypatch.setattr("core.render.ORBIT_HOME", workspace)
    monkeypatch.setattr("core.deliver.ORBIT_DIR", workspace)

    # Create a project
    type_dir = workspace / "💻software"
    type_dir.mkdir()
    proj = type_dir / "💻myproject"
    proj.mkdir()
    (proj / "myproject-project.md").write_text(
        "# 💻myproject\n\n- Tipo: 💻 Software\n- Estado: activo\n"
    )
    (proj / "myproject-logbook.md").write_text(
        "# Logbook\n\n2026-03-19 📝 Test entry #apunte\n"
    )
    (proj / "myproject-agenda.md").write_text(
        "# Agenda\n\n## ✅ Tareas\n- [ ] Test task (2026-03-20)\n"
    )
    notes = proj / "notes"
    notes.mkdir()
    (notes / "2026-03-19_test.md").write_text(
        "# Test note\n\nSome $E = mc^2$ here.\n"
    )

    return {"workspace": workspace, "cloud": cloud, "project": proj,
            "type_dir": type_dir}


def _make_project(type_dir, name, emoji="💻"):
    proj = type_dir / f"{emoji}{name}"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{name}-project.md").write_text(f"# {emoji}{name}\n")
    return proj


# ── Unit tests ────────────────────────────────────────────────────────────────

class TestMdToHtml:
    def test_basic_heading(self):
        html = _md_to_html("# Hello")
        assert "<h1>Hello</h1>" in html

    def test_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |"
        html = _md_to_html(md)
        assert "<table>" in html
        assert "<td>1</td>" in html

    def test_fenced_code(self):
        md = "```python\nprint('hi')\n```"
        html = _md_to_html(md)
        assert "<code" in html
        assert "<pre>" in html

    def test_rewrite_md_links(self):
        html = '<a href="logbook.md">log</a> <a href="notes/test.md">n</a>'
        result = _rewrite_md_links(html)
        assert 'href="logbook.html"' in result
        assert 'href="notes/test.html"' in result

    def test_rewrite_preserves_non_md(self):
        html = '<a href="https://example.com">ext</a>'
        result = _rewrite_md_links(html)
        assert 'href="https://example.com"' in result

    def test_rewrite_preserves_inbox(self):
        html = '<a href="inbox.md">buzón</a>'
        result = _rewrite_md_links(html)
        assert 'href="inbox.md"' in result


# ── Integration tests ────────────────────────────────────────────────────────

class TestRenderProject:
    def test_renders_all_md_files(self, cloud_env):
        n = render_project(cloud_env["project"], cloud_env["cloud"])
        assert n == 4  # project, logbook, agenda, notes/test

    def test_creates_html_files(self, cloud_env):
        render_project(cloud_env["project"], cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        assert (cloud_proj / "myproject-project.html").exists()
        assert (cloud_proj / "myproject-logbook.html").exists()
        assert (cloud_proj / "notes" / "2026-03-19_test.html").exists()

    def test_html_has_katex(self, cloud_env):
        render_project(cloud_env["project"], cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        html = (cloud_proj / "notes" / "2026-03-19_test.html").read_text()
        assert "katex" in html
        assert "E = mc^2" in html

    def test_html_has_css_link(self, cloud_env):
        render_project(cloud_env["project"], cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        html = (cloud_proj / "myproject-project.html").read_text()
        assert "orbit.css" in html

    def test_html_has_nav(self, cloud_env):
        render_project(cloud_env["project"], cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        html = (cloud_proj / "myproject-project.html").read_text()
        assert "index.html" in html

    def test_md_links_rewritten(self, cloud_env):
        # Add a link to logbook in the project file
        pf = cloud_env["project"] / "myproject-project.md"
        pf.write_text("# Project\n\n[logbook](myproject-logbook.md)\n")
        render_project(cloud_env["project"], cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        html = (cloud_proj / "myproject-project.html").read_text()
        assert "myproject-logbook.html" in html

    def test_excludes_inbox(self, cloud_env):
        (cloud_env["project"] / "inbox.md").write_text("- tarea: test\n")
        n = render_project(cloud_env["project"], cloud_env["cloud"])
        assert n == 4  # inbox not counted
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        assert not (cloud_proj / "inbox.html").exists()


class TestRenderAll:
    def test_renders_all_projects(self, cloud_env):
        _make_project(cloud_env["type_dir"], "second")
        n = render_all(cloud_env["cloud"])
        assert n >= 5  # 4 from myproject + 1 from second


class TestRenderIndex:
    def test_creates_index(self, cloud_env):
        ok = render_index(cloud_env["cloud"])
        assert ok
        idx = cloud_env["cloud"] / "index.html"
        assert idx.exists()
        html = idx.read_text()
        assert "orbit.css" in html
        assert "agenda.html" in html
        assert "proyectos.html" in html

    def test_has_inbox_link(self, cloud_env):
        render_index(cloud_env["cloud"])
        html = (cloud_env["cloud"] / "index.html").read_text()
        assert "inbox.md" in html


class TestRenderProyectos:
    def test_creates_proyectos(self, cloud_env):
        ok = render_proyectos(cloud_env["cloud"])
        assert ok
        html = (cloud_env["cloud"] / "proyectos.html").read_text()
        assert "myproject" in html
        assert "myproject-project.html" in html

    def test_has_nav(self, cloud_env):
        render_proyectos(cloud_env["cloud"])
        html = (cloud_env["cloud"] / "proyectos.html").read_text()
        assert "index.html" in html
        assert "agenda.html" in html


class TestRenderAgenda:
    def test_creates_agenda(self, cloud_env):
        ok = render_agenda(cloud_env["cloud"])
        assert ok
        html = (cloud_env["cloud"] / "agenda.html").read_text()
        assert "Agenda" in html

    def test_has_nav(self, cloud_env):
        render_agenda(cloud_env["cloud"])
        html = (cloud_env["cloud"] / "agenda.html").read_text()
        assert "index.html" in html
        assert "proyectos.html" in html


class TestEnsureCloudInboxes:
    def test_creates_global_inbox(self, cloud_env):
        n = ensure_cloud_inboxes(cloud_env["cloud"])
        assert n >= 1
        assert (cloud_env["cloud"] / "inbox.md").exists()

    def test_creates_project_inbox(self, cloud_env):
        ensure_cloud_inboxes(cloud_env["cloud"])
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        assert (cloud_proj / "inbox.md").exists()

    def test_does_not_overwrite_existing(self, cloud_env):
        cloud_proj = cloud_env["cloud"] / "💻software" / "💻myproject"
        cloud_proj.mkdir(parents=True, exist_ok=True)
        (cloud_proj / "inbox.md").write_text("- tarea: existing\n")
        ensure_cloud_inboxes(cloud_env["cloud"])
        assert "existing" in (cloud_proj / "inbox.md").read_text()


class TestSyncCss:
    def test_copies_css(self, cloud_env):
        _sync_css(cloud_env["cloud"])
        assert (cloud_env["cloud"] / "orbit.css").exists()
        content = (cloud_env["cloud"] / "orbit.css").read_text()
        assert "orbit.css" in content or "body" in content
