"""Tests for core/tracked.py — external file tracking registry."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import tracked
from core.tracked import (
    REGISTRY_NAME, FRONTMATTER_KEY,
    load_registry, save_registry, register, unregister, retrack,
    check_entry, apply_refresh, refresh_all,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def project_with_external(tmp_path):
    """Tmp dir with a project dir + an external source .md."""
    proj = tmp_path / "💻test"
    proj.mkdir()
    (proj / "notes").mkdir()
    source = tmp_path / "external_doc.md"
    source.write_text("# Hello\n\nOriginal content.\n")
    return proj, source


# ── Registration ─────────────────────────────────────────────────────────────

class TestRegister:
    def test_register_creates_file_and_registry(self, project_with_external):
        proj, source = project_with_external
        entry = register(proj, "notes/doc.md", source)
        # Registry persisted
        assert (proj / REGISTRY_NAME).exists()
        reg = load_registry(proj)
        assert "notes/doc.md" in reg
        assert reg["notes/doc.md"]["source"] == str(source.resolve())
        assert entry["sha256"]
        # File written with frontmatter
        dest = proj / "notes" / "doc.md"
        assert dest.exists()
        text = dest.read_text()
        assert FRONTMATTER_KEY in text
        assert "Original content" in text

    def test_register_rejects_non_md(self, project_with_external):
        proj, _ = project_with_external
        pdf = proj.parent / "file.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with pytest.raises(ValueError, match=".md"):
            register(proj, "notes/doc.md", pdf)

    def test_register_missing_source_raises(self, project_with_external):
        proj, _ = project_with_external
        with pytest.raises(FileNotFoundError):
            register(proj, "notes/x.md", Path("/nonexistent/file.md"))


# ── Refresh outcomes ─────────────────────────────────────────────────────────

class TestCheckEntry:
    def test_clean_when_nothing_changed(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        reg = load_registry(proj)
        outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert outcome.status == "clean"

    def test_refreshed_when_source_changes(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        source.write_text("# Hello\n\nUpdated content.\n")
        reg = load_registry(proj)
        outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert outcome.status == "refreshed"

    def test_dest_tampered_when_dest_edited(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        # User edits the mirrored copy by mistake
        dest = proj / "notes" / "doc.md"
        dest.write_text(dest.read_text() + "\n\n## My addition\n")
        reg = load_registry(proj)
        outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert outcome.status == "dest_tampered"
        assert "edit" in outcome.detail.lower()

    def test_conflict_when_both_change(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        source.write_text("# Hello\n\nNew from source.\n")
        dest = proj / "notes" / "doc.md"
        dest.write_text(dest.read_text() + "\n\n## My addition\n")
        reg = load_registry(proj)
        outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert outcome.status == "conflict"

    def test_source_missing(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        source.unlink()
        reg = load_registry(proj)
        outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert outcome.status == "source_missing"


# ── refresh_all flow ─────────────────────────────────────────────────────────

class TestRefreshAll:
    def test_refresh_applies_source_changes(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        source.write_text("# Updated\n")
        outcomes = refresh_all([proj], force=False)
        assert len(outcomes) == 1
        assert outcomes[0].status == "refreshed"
        dest = proj / "notes" / "doc.md"
        assert "Updated" in dest.read_text()
        # Registry's stored sha updated
        reg = load_registry(proj)
        new_outcome = check_entry(proj, "notes/doc.md", reg["notes/doc.md"])
        assert new_outcome.status == "clean"

    def test_refresh_skips_tampered_without_force(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        dest = proj / "notes" / "doc.md"
        original = dest.read_text()
        dest.write_text(original + "\n\nlocal edits\n")
        outcomes = refresh_all([proj], force=False)
        assert outcomes[0].status == "dest_tampered"
        # Dest still has local edits (not overwritten)
        assert "local edits" in dest.read_text()

    def test_refresh_with_force_discards_tampering(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        dest = proj / "notes" / "doc.md"
        dest.write_text(dest.read_text() + "\n\nlocal edits\n")
        outcomes = refresh_all([proj], force=True)
        assert outcomes[0].status == "refreshed"
        # Local edits are now gone
        assert "local edits" not in dest.read_text()


# ── Registry ops ─────────────────────────────────────────────────────────────

class TestUnregister:
    def test_unregister_removes_entry(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        assert unregister(proj, "notes/doc.md") is True
        assert load_registry(proj) == {}
        # File kept by default
        assert (proj / "notes" / "doc.md").exists()

    def test_unregister_with_delete(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        unregister(proj, "notes/doc.md", keep_file=False)
        assert not (proj / "notes" / "doc.md").exists()

    def test_empty_registry_file_is_deleted(self, project_with_external):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        unregister(proj, "notes/doc.md")
        # Empty → file removed
        assert not (proj / REGISTRY_NAME).exists()


class TestRetrack:
    def test_retrack_repoints_source(self, project_with_external, tmp_path):
        proj, source = project_with_external
        register(proj, "notes/doc.md", source)
        new_source = tmp_path / "new_doc.md"
        new_source.write_text("# Different content\n")
        retrack(proj, "notes/doc.md", new_source)
        reg = load_registry(proj)
        assert reg["notes/doc.md"]["source"] == str(new_source.resolve())
        assert "Different content" in (proj / "notes" / "doc.md").read_text()

    def test_retrack_missing_entry_raises(self, project_with_external, tmp_path):
        proj, _ = project_with_external
        other = tmp_path / "z.md"
        other.write_text("x")
        with pytest.raises(KeyError):
            retrack(proj, "notes/never_tracked.md", other)
