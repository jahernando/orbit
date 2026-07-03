"""test_link_import — unit tests for core.link_import."""

import json
import os
import sys
from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated orbit env with one project under ⚙️gestion/⚙️catedra/."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    cloud_root = tmp_path / "cloud" / "🚀test-ws"
    cloud_root.mkdir(parents=True)

    (workspace / "orbit.json").write_text(json.dumps({
        "space": "test-ws",
        "emoji": "🚀",
        "cloud_root": str(cloud_root),
        "types": {
            "gestion": "⚙️",
            "docencia": "📚",
        },
    }, ensure_ascii=False))

    gestion_dir = workspace / "⚙️gestion"
    gestion_dir.mkdir()
    proj = gestion_dir / "⚙️catedra"
    proj.mkdir()
    (proj / "notes").mkdir()

    import core.config as cfg
    import core.log as cl
    import core.deliver as dlv
    monkeypatch.setattr(cfg, "ORBIT_HOME", workspace)
    monkeypatch.setattr(cfg, "_ORBIT_JSON", workspace / "orbit.json")
    monkeypatch.setattr(cfg, "PROJECTS_DIR", workspace)
    monkeypatch.setattr(cfg, "_orbit_emoji", "🚀")
    monkeypatch.setattr(cfg, "ORBIT_SPACE", "test-ws")
    monkeypatch.setattr(cl, "PROJECTS_DIR", workspace)
    monkeypatch.setattr(dlv, "ORBIT_DIR", workspace)

    return {
        "workspace": workspace,
        "cloud_root": cloud_root,
        "proj": proj,
    }


# ══════════════════════════════════════════════════════════════════════════════
# apply_mode — .md routing
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyModeMd:
    def test_md_link_creates_symlink_in_notes(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "DECISIONS.md"
        src.write_text("# Decisions\n")
        rel, dest = apply_mode(env["proj"], src, "link", non_md_subdir="logs")
        assert rel == "./notes/DECISIONS.md"
        assert dest == env["proj"] / "notes" / "DECISIONS.md"
        assert dest.is_symlink()
        assert dest.resolve() == src.resolve()

    def test_md_link_registers_in_tracked(self, env, tmp_path):
        from core.link_import import apply_mode
        from core.tracked import load_registry
        src = tmp_path / "shared.md"
        src.write_text("# Shared\n")
        apply_mode(env["proj"], src, "link", non_md_subdir="logs")
        files = load_registry(env["proj"])
        assert "shared.md" in files
        assert files["shared.md"] == str(src.resolve())

    def test_md_import_copies_to_notes(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "snapshot.md"
        src.write_text("# Snap\n")
        rel, dest = apply_mode(env["proj"], src, "import", non_md_subdir="logs")
        assert rel == "./notes/snapshot.md"
        assert dest == env["proj"] / "notes" / "snapshot.md"
        assert not dest.is_symlink()
        assert dest.read_text() == "# Snap\n"

    def test_md_import_not_in_tracked(self, env, tmp_path):
        from core.link_import import apply_mode
        from core.tracked import load_registry
        src = tmp_path / "owned.md"
        src.write_text("# Owned\n")
        apply_mode(env["proj"], src, "import", non_md_subdir="logs")
        # Propia copies are not registered as externa
        assert "owned.md" not in load_registry(env["proj"])

    def test_md_strips_diacritics(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "Investigación.md"
        src.write_text("# Inv\n")
        rel, dest = apply_mode(env["proj"], src, "import", non_md_subdir="logs")
        # NFD-decomposed accent stripped → "Investigacion.md"
        assert dest.name == "Investigacion.md"
        assert rel == "./notes/Investigacion.md"

    def test_md_date_prefix(self, env, tmp_path):
        from core.link_import import apply_mode
        from datetime import date
        src = tmp_path / "report.md"
        src.write_text("# R\n")
        rel, dest = apply_mode(env["proj"], src, "import",
                               non_md_subdir="logs", date_prefix=True)
        today = date.today().isoformat()
        assert dest.name == f"{today}_report.md"
        assert rel == f"./notes/{today}_report.md"

    def test_md_conflict_raises(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "dup.md"
        src.write_text("# Dup\n")
        apply_mode(env["proj"], src, "import", non_md_subdir="logs")
        with pytest.raises(FileExistsError):
            apply_mode(env["proj"], src, "import", non_md_subdir="logs")


# ══════════════════════════════════════════════════════════════════════════════
# apply_mode — non-md routing
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyModeNonMd:
    def test_pdf_import_copies_to_cloud(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "paper.pdf"
        src.write_bytes(b"%PDF-test")
        rel, dest = apply_mode(env["proj"], src, "import",
                               non_md_subdir="logs", date_prefix=True)
        from datetime import date
        today = date.today().isoformat()
        assert rel == f"./cloud/logs/{today}_paper.pdf"
        assert "⚙️gestion" in str(dest)
        assert dest.name == f"{today}_paper.pdf"
        assert not dest.is_symlink()
        assert dest.read_bytes() == b"%PDF-test"

    def test_pdf_link_creates_symlink_in_cloud(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "ref.pdf"
        src.write_bytes(b"%PDF-ref")
        rel, dest = apply_mode(env["proj"], src, "link", non_md_subdir="logs")
        assert rel == "./cloud/logs/ref.pdf"
        assert dest.is_symlink()
        assert dest.resolve() == src.resolve()

    def test_non_md_uses_subdir(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "fig.png"
        src.write_bytes(b"\x89PNG")
        rel, _ = apply_mode(env["proj"], src, "import", non_md_subdir="hls")
        assert rel == "./cloud/hls/fig.png"

    def test_non_md_no_diacritic_strip(self, env, tmp_path):
        # Only .md files are renamed (Obsidian concern). PDFs keep names.
        from core.link_import import apply_mode
        src = tmp_path / "paréntesis.pdf"
        src.write_bytes(b"%PDF")
        rel, dest = apply_mode(env["proj"], src, "import", non_md_subdir="logs")
        assert "paréntesis.pdf" in dest.name


# ══════════════════════════════════════════════════════════════════════════════
# apply_mode — errors
# ══════════════════════════════════════════════════════════════════════════════

class TestApplyModeErrors:
    def test_missing_source(self, env):
        from core.link_import import apply_mode
        with pytest.raises(FileNotFoundError):
            apply_mode(env["proj"], Path("/nope/missing.md"),
                       "link", non_md_subdir="logs")

    def test_directory_source(self, env, tmp_path):
        from core.link_import import apply_mode
        d = tmp_path / "adir"
        d.mkdir()
        with pytest.raises(ValueError, match="directorio"):
            apply_mode(env["proj"], d, "link", non_md_subdir="logs")

    def test_unknown_mode(self, env, tmp_path):
        from core.link_import import apply_mode
        src = tmp_path / "x.md"
        src.write_text("x")
        with pytest.raises(ValueError, match="modo"):
            apply_mode(env["proj"], src, "deliver", non_md_subdir="logs")


# ══════════════════════════════════════════════════════════════════════════════
# resolve_mode + ask_mode
# ══════════════════════════════════════════════════════════════════════════════

class TestResolveMode:
    def test_link_flag(self):
        from core.link_import import resolve_mode
        assert resolve_mode(as_link=True, as_import=False) == "link"

    def test_import_flag(self):
        from core.link_import import resolve_mode
        assert resolve_mode(as_link=False, as_import=True) == "import"

    def test_mutex_raises(self):
        from core.link_import import resolve_mode
        with pytest.raises(ValueError, match="mutuamente exclusivos"):
            resolve_mode(as_link=True, as_import=True)

    def test_neither_flag_no_tty_defaults_link(self, monkeypatch):
        # Non-tty scripts default to 'link' (conservative — no file movement).
        from core.link_import import resolve_mode
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert resolve_mode(as_link=False, as_import=False) == "link"


class TestAskMode:
    def test_empty_input_default_import(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "")
        assert li.ask_mode() == "import"

    def test_i_returns_import(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "i")
        assert li.ask_mode() == "import"

    def test_l_returns_link(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "l")
        assert li.ask_mode() == "link"

    def test_uppercase_works(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "L")
        assert li.ask_mode() == "link"

    def test_invalid_input_reprompts(self, monkeypatch, capsys):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        answers = iter(["foo", "x", "l"])
        monkeypatch.setattr("builtins.input", lambda *a, **kw: next(answers))
        assert li.ask_mode() == "link"
        out = capsys.readouterr().out
        assert out.count("no reconocida") == 2

    def test_non_tty_defaults_link(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert li.ask_mode() == "link"

    def test_eof_defaults_import(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        def raise_eof(*a, **kw): raise EOFError
        monkeypatch.setattr("builtins.input", raise_eof)
        assert li.ask_mode() == "import"

    def test_q_raises_cancel(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "q")
        with pytest.raises(ValueError, match="Cancelado"):
            li.ask_mode()

    def test_quit_word_raises_cancel(self, monkeypatch):
        import core.link_import as li
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a, **kw: "quit")
        with pytest.raises(ValueError, match="Cancelado"):
            li.ask_mode()
