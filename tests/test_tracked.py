"""Tests for core/tracked.py — propia/externa model (v0.36)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core import tracked
from core.tracked import (
    REGISTRY_NAME,
    load_registry, save_registry,
    track, untrack, iter_tracked, check_status, resolve_target, is_external,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def project_with_external(tmp_path):
    """tmp_path with a project dir and an external source .md (sibling)."""
    proj = tmp_path / "💻test"
    proj.mkdir()
    (proj / "notes").mkdir()
    source = tmp_path / "external_doc.md"
    source.write_text("# Hello\n\nOriginal content.\n")
    return proj, source


# ── track / untrack ─────────────────────────────────────────────────────────

class TestTrack:
    def test_creates_relative_symlink(self, project_with_external):
        proj, source = project_with_external
        name = track(proj, source)
        assert name == "external_doc.md"
        link = proj / "notes" / name
        assert link.is_symlink()
        # Stored target is relative (not absolute).
        raw_target = os.readlink(link)
        assert not raw_target.startswith("/")
        # And it resolves back to the real source.
        assert link.resolve() == source.resolve()

    def test_registry_persisted_v036_schema(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        reg_path = proj / REGISTRY_NAME
        raw = json.loads(reg_path.read_text())
        assert "files" in raw
        assert "external_doc.md" in raw["files"]
        assert raw["files"]["external_doc.md"] == str(source.resolve())

    def test_track_rejects_non_md(self, project_with_external, tmp_path):
        proj, _ = project_with_external
        pdf = tmp_path / "foo.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with pytest.raises(ValueError, match=".md"):
            track(proj, pdf)

    def test_track_rejects_directory(self, project_with_external, tmp_path):
        proj, _ = project_with_external
        d = tmp_path / "subdir"
        d.mkdir()
        with pytest.raises(ValueError, match="directorio"):
            track(proj, d)

    def test_track_missing_source_raises(self, project_with_external):
        proj, _ = project_with_external
        with pytest.raises(FileNotFoundError):
            track(proj, Path("/nonexistent/file.md"))

    def test_track_explicit_name(self, project_with_external):
        proj, source = project_with_external
        name = track(proj, source, name="ALIAS.md")
        assert name == "ALIAS.md"
        assert (proj / "notes" / "ALIAS.md").is_symlink()
        reg = load_registry(proj)
        assert "ALIAS.md" in reg

    def test_track_conflict_existing_file(self, project_with_external):
        proj, source = project_with_external
        # An existing propia with the same basename.
        (proj / "notes" / "external_doc.md").write_text("propia content")
        with pytest.raises(FileExistsError):
            track(proj, source)


class TestUntrack:
    def test_removes_symlink_and_entry(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        assert untrack(proj, "external_doc.md") is True
        assert not (proj / "notes" / "external_doc.md").exists()
        assert load_registry(proj) == {}
        # Source intact.
        assert source.exists()
        assert "Original content" in source.read_text()

    def test_untrack_missing_returns_false(self, project_with_external):
        proj, _ = project_with_external
        assert untrack(proj, "never_tracked.md") is False

    def test_empty_registry_file_is_removed(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        untrack(proj, "external_doc.md")
        assert not (proj / REGISTRY_NAME).exists()


# ── Status checks ────────────────────────────────────────────────────────────

class TestCheckStatus:
    def test_ok_when_link_and_target_present(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        assert check_status(proj, "external_doc.md") == "ok"

    def test_broken_link_when_target_gone(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        source.unlink()
        assert check_status(proj, "external_doc.md") == "broken_link"

    def test_missing_link_when_symlink_deleted(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        (proj / "notes" / "external_doc.md").unlink()
        assert check_status(proj, "external_doc.md") == "missing_link"

    def test_not_link_when_real_file_in_place(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        # User accidentally replaced the symlink with a plain file.
        link = proj / "notes" / "external_doc.md"
        link.unlink()
        link.write_text("plain content")
        assert check_status(proj, "external_doc.md") == "not_link"

    def test_not_tracked_when_unregistered(self, project_with_external):
        proj, _ = project_with_external
        assert check_status(proj, "anything.md") == "not_tracked"


# ── resolve_target / is_external ────────────────────────────────────────────

class TestResolveAndIsExternal:
    def test_resolve_target_returns_source(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        resolved = resolve_target(proj, "external_doc.md")
        assert resolved == source.resolve()

    def test_resolve_returns_none_when_broken(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        source.unlink()
        assert resolve_target(proj, "external_doc.md") is None

    def test_is_external_true_for_tracked(self, project_with_external):
        proj, source = project_with_external
        track(proj, source)
        assert is_external(proj, proj / "notes" / "external_doc.md")

    def test_is_external_false_for_propia(self, project_with_external):
        proj, _ = project_with_external
        propia = proj / "notes" / "propia.md"
        propia.write_text("# mine")
        assert is_external(proj, propia) is False


# ── iter_tracked ─────────────────────────────────────────────────────────────

class TestIterTracked:
    def test_yields_across_projects(self, tmp_path):
        p1 = tmp_path / "p1"; (p1 / "notes").mkdir(parents=True)
        p2 = tmp_path / "p2"; (p2 / "notes").mkdir(parents=True)
        s1 = tmp_path / "a.md"; s1.write_text("A")
        s2 = tmp_path / "b.md"; s2.write_text("B")
        track(p1, s1)
        track(p2, s2)
        got = sorted([(pd.name, name) for pd, name, _ in iter_tracked([p1, p2])])
        assert got == [("p1", "a.md"), ("p2", "b.md")]


# ── Backward read of v0.34 registry ──────────────────────────────────────────

class TestReadLegacyRegistry:
    def test_load_v034_returns_flat_dict(self, project_with_external):
        proj, source = project_with_external
        # Write a v0.34 registry by hand.
        legacy = {
            "notes/decisions.md": {
                "source": "/tmp/DECISIONS.md",
                "sha256": "abc",
                "added": "2026-05-13",
            }
        }
        (proj / REGISTRY_NAME).write_text(json.dumps(legacy))
        reg = load_registry(proj)
        assert reg == {"decisions.md": "/tmp/DECISIONS.md"}


# ── Migration ────────────────────────────────────────────────────────────────

class TestMigration:
    def _write_legacy(self, proj, source, name="decisions.md", tampered=False):
        """Recreate v0.34 state: copy + frontmatter + legacy registry.

        Computes the real sha256 of the copy and stores it. If ``tampered``,
        appends an extra line to the copy *after* hashing — simulating the
        user editing the mirror after the last refresh.
        """
        import hashlib
        copy = proj / "notes" / name
        body = source.read_text()
        copy.write_text(f"---\norbit_tracked_from: {source}\n---\n{body}")
        sha = hashlib.sha256(copy.read_bytes()).hexdigest()
        if tampered:
            copy.write_text(copy.read_text() + "\n\nuser edit\n")
        legacy = {
            f"notes/{name}": {
                "source": str(source),
                "sha256": sha,
                "added": "2026-05-13",
            }
        }
        (proj / REGISTRY_NAME).write_text(json.dumps(legacy))

    def test_migrate_clean_entry(self, project_with_external):
        from core.tracked_migrate import migrate_project
        proj, source = project_with_external
        self._write_legacy(proj, source)
        summary = migrate_project(proj)
        assert summary["migrated"] == ["decisions.md"]
        assert summary["tampered"] == []
        link = proj / "notes" / "decisions.md"
        assert link.is_symlink()
        reg = load_registry(proj)
        assert reg == {"decisions.md": str(source)}

    def test_migrate_aborts_on_tampered(self, project_with_external):
        from core.tracked_migrate import migrate_project
        proj, source = project_with_external
        self._write_legacy(proj, source, tampered=True)
        summary = migrate_project(proj)
        assert summary["migrated"] == []
        assert len(summary["tampered"]) == 1
        # Copy untouched, registry untouched (still v0.34).
        copy = proj / "notes" / "decisions.md"
        assert not copy.is_symlink()
        assert "user edit" in copy.read_text()

    def test_migrate_dry_run_no_changes(self, project_with_external):
        from core.tracked_migrate import migrate_project
        proj, source = project_with_external
        self._write_legacy(proj, source)
        summary = migrate_project(proj, dry_run=True)
        assert summary["migrated"] == ["decisions.md"]
        # Filesystem untouched.
        copy = proj / "notes" / "decisions.md"
        assert not copy.is_symlink()
        # Registry still legacy.
        raw = json.loads((proj / REGISTRY_NAME).read_text())
        assert "notes/decisions.md" in raw

    def test_migrate_idempotent(self, project_with_external):
        from core.tracked_migrate import migrate_project
        proj, source = project_with_external
        self._write_legacy(proj, source)
        migrate_project(proj)
        summary = migrate_project(proj)   # second run: no-op
        assert summary["migrated"] == []
        assert summary["tampered"] == []
