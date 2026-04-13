"""test_cloud_imgs.py — unit tests for cloud image collection.

Covers:
  - _list_pending_images:   lists images in _imgs/
  - _find_references:       finds .md files referencing an image
  - _note_stem / _note_date: filename parsing for rename
  - _build_new_name:        renaming logic with fig indexing
  - _update_link_in_file:   wikilink and markdown link rewriting
  - run_cloud_imgs:         end-to-end: scan, match, rename, move, update
  - check_pending_imgs:     doctor integration
"""

import json
from datetime import date
from pathlib import Path

import pytest


@pytest.fixture
def imgs_env(tmp_path, monkeypatch):
    """Isolated orbit environment with _imgs/ and a project."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    cloud_root = tmp_path / "cloud" / "🚀test-ws"
    cloud_root.mkdir(parents=True)

    config = {
        "space": "test-ws",
        "emoji": "🚀",
        "cloud_root": str(cloud_root),
        "types": {"software": "💻"},
    }
    (workspace / "orbit.json").write_text(json.dumps(config, ensure_ascii=False))

    # Type dir + project
    type_dir = workspace / "💻software"
    type_dir.mkdir()
    proj = type_dir / "💻mi-proyecto"
    proj.mkdir()
    (proj / "notes").mkdir()

    # Create cloud symlink target
    cloud_proj = cloud_root / "💻software" / "💻mi-proyecto" / "cloud"
    cloud_proj.mkdir(parents=True)
    (proj / "cloud").symlink_to(cloud_proj)

    # _imgs/ directory
    imgs_dir = workspace / "_imgs"
    imgs_dir.mkdir()

    # Monkeypatch
    import core.config as cfg
    import core.log as cl
    import core.deliver as dlv
    import core.cloud_imgs as ci

    monkeypatch.setattr(cfg, "ORBIT_HOME", workspace)
    monkeypatch.setattr(cfg, "_ORBIT_JSON", workspace / "orbit.json")
    monkeypatch.setattr(cfg, "PROJECTS_DIR", workspace)
    monkeypatch.setattr(cl, "PROJECTS_DIR", workspace)
    monkeypatch.setattr(dlv, "ORBIT_DIR", workspace)
    monkeypatch.setattr(ci, "ORBIT_HOME", workspace)

    return {
        "workspace": workspace,
        "proj": proj,
        "imgs_dir": imgs_dir,
        "cloud_proj": cloud_proj,
    }


# ══════════════════════════════════════════════════════════════════════════════
# _list_pending_images
# ══════════════════════════════════════════════════════════════════════════════

class TestListPendingImages:

    def test_empty_dir(self, imgs_env):
        from core.cloud_imgs import _list_pending_images
        assert _list_pending_images() == []

    def test_lists_images_only(self, imgs_env):
        from core.cloud_imgs import _list_pending_images
        d = imgs_env["imgs_dir"]
        (d / "photo.png").write_bytes(b"\x89PNG")
        (d / "readme.txt").write_text("not an image")
        (d / "fig.jpg").write_bytes(b"\xff\xd8")
        result = _list_pending_images()
        names = [f.name for f in result]
        assert "photo.png" in names
        assert "fig.jpg" in names
        assert "readme.txt" not in names

    def test_no_dir(self, imgs_env):
        from core.cloud_imgs import _list_pending_images
        import shutil
        shutil.rmtree(imgs_env["imgs_dir"])
        assert _list_pending_images() == []


# ══════════════════════════════════════════════════════════════════════════════
# _note_stem / _note_date
# ══════════════════════════════════════════════════════════════════════════════

class TestNoteStemDate:

    def test_date_prefixed(self):
        from core.cloud_imgs import _note_stem, _note_date
        p = Path("2026-03-25_resultados.md")
        assert _note_stem(p) == "resultados"
        assert _note_date(p) == "2026-03-25"

    def test_plain_name(self):
        from core.cloud_imgs import _note_stem, _note_date
        p = Path("logbook.md")
        assert _note_stem(p) == "logbook"
        assert _note_date(p) == date.today().isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# _build_new_name
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildNewName:

    def test_single_fig(self):
        from core.cloud_imgs import _build_new_name
        img = Path("Pasted image 20260325.png")
        md = Path("2026-03-25_resultados.md")
        assert _build_new_name(img, md, 1, 1) == "2026-03-25_resultados.png"

    def test_multiple_figs(self):
        from core.cloud_imgs import _build_new_name
        img = Path("Captura.png")
        md = Path("2026-03-25_resultados.md")
        assert _build_new_name(img, md, 1, 3) == "2026-03-25_resultados_fig1.png"
        assert _build_new_name(img, md, 2, 3) == "2026-03-25_resultados_fig2.png"

    def test_preserves_extension(self):
        from core.cloud_imgs import _build_new_name
        img = Path("screenshot.jpg")
        md = Path("logbook.md")
        name = _build_new_name(img, md, 1, 1)
        assert name.endswith(".jpg")
        assert "logbook" in name

    def test_uppercase_ext_normalized(self):
        from core.cloud_imgs import _build_new_name
        img = Path("Photo.PNG")
        md = Path("2026-01-01_test.md")
        assert _build_new_name(img, md, 1, 1).endswith(".png")


# ══════════════════════════════════════════════════════════════════════════════
# _find_references
# ══════════════════════════════════════════════════════════════════════════════

class TestFindReferences:

    def test_finds_wikilink(self, imgs_env):
        from core.cloud_imgs import _find_references
        proj = imgs_env["proj"]
        note = proj / "notes" / "2026-03-25_test.md"
        note.write_text("# Test\n\n![[Pasted image 20260325.png]]\n")
        refs = _find_references("Pasted image 20260325.png")
        assert len(refs) == 1
        assert refs[0][0] == note
        assert refs[0][1] == proj

    def test_finds_markdown_img(self, imgs_env):
        from core.cloud_imgs import _find_references
        proj = imgs_env["proj"]
        note = proj / "notes" / "2026-03-25_test.md"
        note.write_text("# Test\n\n![alt](Pasted image 20260325.png)\n")
        refs = _find_references("Pasted image 20260325.png")
        assert len(refs) == 1

    def test_no_reference(self, imgs_env):
        from core.cloud_imgs import _find_references
        proj = imgs_env["proj"]
        note = proj / "notes" / "2026-03-25_test.md"
        note.write_text("# Test\nNo images here\n")
        refs = _find_references("ghost.png")
        assert refs == []

    def test_skips_cloud_dir(self, imgs_env):
        from core.cloud_imgs import _find_references
        proj = imgs_env["proj"]
        # Put a .md inside cloud/ — should be ignored
        cloud_md = proj / "cloud" / "index.md"
        cloud_md.parent.mkdir(parents=True, exist_ok=True)
        cloud_md.write_text("![[test.png]]\n")
        note = proj / "notes" / "real.md"
        note.write_text("# Real\n![[test.png]]\n")
        refs = _find_references("test.png")
        assert len(refs) == 1
        assert refs[0][0] == note


# ══════════════════════════════════════════════════════════════════════════════
# _update_link_in_file
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateLinkInFile:

    def test_wikilink_replaced(self, tmp_path):
        from core.cloud_imgs import _update_link_in_file
        md = tmp_path / "note.md"
        md.write_text("# Test\n\n![[Pasted image.png]]\n\nMore text.\n")
        result = _update_link_in_file(md, "Pasted image.png",
                                      "./cloud/imgs/2026-03-25_test.png")
        assert result is True
        content = md.read_text()
        assert "![[" not in content
        assert "![](./cloud/imgs/2026-03-25_test.png)" in content

    def test_markdown_img_replaced(self, tmp_path):
        from core.cloud_imgs import _update_link_in_file
        md = tmp_path / "note.md"
        md.write_text("![alt](imgs/photo.png)\n")
        result = _update_link_in_file(md, "photo.png",
                                      "./cloud/imgs/2026-03-25_note.png")
        assert result is True
        content = md.read_text()
        assert "![alt](./cloud/imgs/2026-03-25_note.png)" in content

    def test_no_match_returns_false(self, tmp_path):
        from core.cloud_imgs import _update_link_in_file
        md = tmp_path / "note.md"
        md.write_text("# No images\n")
        assert _update_link_in_file(md, "ghost.png", "./cloud/imgs/x.png") is False

    def test_wikilink_without_extension(self, tmp_path):
        from core.cloud_imgs import _update_link_in_file
        md = tmp_path / "note.md"
        md.write_text("![[Pasted image]]\n")
        result = _update_link_in_file(md, "Pasted image.png",
                                      "./cloud/imgs/fig.png")
        assert result is True
        assert "![](./cloud/imgs/fig.png)" in md.read_text()


# ══════════════════════════════════════════════════════════════════════════════
# run_cloud_imgs (end-to-end)
# ══════════════════════════════════════════════════════════════════════════════

class TestRunCloudImgs:

    def test_no_images(self, imgs_env, capsys):
        from core.cloud_imgs import run_cloud_imgs
        ret = run_cloud_imgs()
        assert ret == 0
        assert "No hay imágenes" in capsys.readouterr().out

    def test_moves_and_renames(self, imgs_env):
        from core.cloud_imgs import run_cloud_imgs
        proj = imgs_env["proj"]
        imgs_dir = imgs_env["imgs_dir"]

        # Create image in _imgs/
        img = imgs_dir / "Pasted image 20260325.png"
        img.write_bytes(b"\x89PNG-fake")

        # Create note referencing it
        note = proj / "notes" / "2026-03-25_experimento.md"
        note.write_text("# Experimento\n\n![[Pasted image 20260325.png]]\n")

        ret = run_cloud_imgs()
        assert ret == 0

        # Image moved from _imgs/
        assert not img.exists()

        # Image in cloud/imgs/ with new name
        cloud_imgs = proj / "cloud" / "imgs"
        delivered = list(cloud_imgs.iterdir())
        assert len(delivered) == 1
        assert delivered[0].name == "2026-03-25_experimento.png"

        # Link updated in note
        content = note.read_text()
        assert "![[" not in content
        assert "cloud/imgs/2026-03-25_experimento.png" in content

    def test_multiple_figures_indexed(self, imgs_env):
        from core.cloud_imgs import run_cloud_imgs
        proj = imgs_env["proj"]
        imgs_dir = imgs_env["imgs_dir"]

        (imgs_dir / "img_a.png").write_bytes(b"\x89PNG")
        (imgs_dir / "img_b.png").write_bytes(b"\x89PNG")

        note = proj / "notes" / "2026-03-25_paper.md"
        note.write_text("# Paper\n![[img_a.png]]\n![[img_b.png]]\n")

        run_cloud_imgs()

        cloud_imgs = proj / "cloud" / "imgs"
        names = sorted(f.name for f in cloud_imgs.iterdir())
        assert "2026-03-25_paper_fig1.png" in names
        assert "2026-03-25_paper_fig2.png" in names

    def test_orphan_reported(self, imgs_env, capsys):
        from core.cloud_imgs import run_cloud_imgs
        imgs_dir = imgs_env["imgs_dir"]
        (imgs_dir / "orphan.png").write_bytes(b"\x89PNG")

        run_cloud_imgs()

        out = capsys.readouterr().out
        assert "huérfana" in out
        assert "orphan.png" in out
        # Orphan stays in _imgs/
        assert (imgs_dir / "orphan.png").exists()

    def test_dry_run(self, imgs_env, capsys):
        from core.cloud_imgs import run_cloud_imgs
        proj = imgs_env["proj"]
        imgs_dir = imgs_env["imgs_dir"]

        img = imgs_dir / "test.png"
        img.write_bytes(b"\x89PNG")
        note = proj / "notes" / "2026-03-25_demo.md"
        note.write_text("![[test.png]]\n")

        run_cloud_imgs(dry_run=True)

        # Image NOT moved
        assert img.exists()
        # Link NOT changed
        assert "![[test.png]]" in note.read_text()
        out = capsys.readouterr().out
        assert "📋" in out

    def test_logbook_reference(self, imgs_env):
        """Image referenced from logbook.md (no date prefix in filename)."""
        from core.cloud_imgs import run_cloud_imgs
        proj = imgs_env["proj"]
        imgs_dir = imgs_env["imgs_dir"]

        (imgs_dir / "screenshot.png").write_bytes(b"\x89PNG")
        logbook = proj / "logbook.md"
        logbook.write_text("# Logbook\n2026-03-25 📝 #apunte Nota con ![[screenshot.png]]\n")

        run_cloud_imgs()

        cloud_imgs = proj / "cloud" / "imgs"
        delivered = list(cloud_imgs.iterdir())
        assert len(delivered) == 1
        # Date from today, stem = "logbook"
        assert "logbook" in delivered[0].name


# ══════════════════════════════════════════════════════════════════════════════
# check_pending_imgs (doctor integration)
# ══════════════════════════════════════════════════════════════════════════════

class TestCheckPendingImgs:

    def test_returns_count(self, imgs_env):
        from core.cloud_imgs import check_pending_imgs
        assert check_pending_imgs() == 0
        (imgs_env["imgs_dir"] / "a.png").write_bytes(b"\x89PNG")
        (imgs_env["imgs_dir"] / "b.jpg").write_bytes(b"\xff\xd8")
        assert check_pending_imgs() == 2

    def test_ignores_non_images(self, imgs_env):
        from core.cloud_imgs import check_pending_imgs
        (imgs_env["imgs_dir"] / "notes.txt").write_text("text")
        assert check_pending_imgs() == 0
