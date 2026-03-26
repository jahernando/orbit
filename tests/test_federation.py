"""test_federation.py — unit tests for workspace federation (read-only).

Covers:
  - Loading federation.json
  - iter_federated_project_dirs yields local + federated projects
  - iter_federated_project_dirs(include_federated=False) yields local only
  - get_federation_emoji returns emoji for federated, empty for local
  - is_federated returns True/False correctly
  - iter_project_dirs unchanged (local only)
"""

import json
import pytest
from pathlib import Path

from core.config import (
    iter_project_dirs,
    iter_federated_project_dirs,
    get_federation_emoji,
    is_federated,
)


@pytest.fixture
def fed_env(tmp_path, monkeypatch):
    """Set up two workspaces: main (work) and federated (personal)."""
    # Main workspace
    main_ws = tmp_path / "work"
    main_ws.mkdir()
    main_json = main_ws / "orbit.json"
    main_json.write_text(json.dumps({
        "space": "work",
        "emoji": "🚀",
        "types": {"software": "💻", "investigacion": "🌀"},
    }, ensure_ascii=False))

    # Create projects in main
    (main_ws / "💻software" / "💻orbit").mkdir(parents=True)
    (main_ws / "🌀investigacion" / "🌀paper1").mkdir(parents=True)

    # Personal workspace
    personal_ws = tmp_path / "personal"
    personal_ws.mkdir()
    personal_json = personal_ws / "orbit.json"
    personal_json.write_text(json.dumps({
        "space": "personal",
        "emoji": "🌿",
        "types": {"familia": "🤗", "aficiones": "🎨"},
    }, ensure_ascii=False))

    # Create projects in personal
    (personal_ws / "🤗familia" / "🤗casa").mkdir(parents=True)
    (personal_ws / "🎨aficiones" / "🎨musica").mkdir(parents=True)

    # Federation config in main
    fed_json = main_ws / "federation.json"
    fed_json.write_text(json.dumps({
        "federated": [
            {"name": "personal", "path": str(personal_ws), "emoji": "🌿"}
        ]
    }, ensure_ascii=False))

    # Patch config module
    monkeypatch.setattr("core.config.ORBIT_HOME", main_ws)
    monkeypatch.setattr("core.config._ORBIT_JSON", main_json)
    monkeypatch.setattr("core.config._FEDERATION_PATH", fed_json)

    # Reload federation config
    fed_cfg = json.loads(fed_json.read_text())
    monkeypatch.setattr("core.config._FEDERATED_SPACES",
                        fed_cfg.get("federated", []))

    return main_ws, personal_ws


@pytest.fixture
def no_fed_env(tmp_path, monkeypatch):
    """Workspace without federation.json."""
    ws = tmp_path / "solo"
    ws.mkdir()
    ws_json = ws / "orbit.json"
    ws_json.write_text(json.dumps({
        "types": {"software": "💻"},
    }, ensure_ascii=False))
    (ws / "💻software" / "💻app").mkdir(parents=True)

    monkeypatch.setattr("core.config.ORBIT_HOME", ws)
    monkeypatch.setattr("core.config._ORBIT_JSON", ws_json)
    monkeypatch.setattr("core.config._FEDERATED_SPACES", [])

    return ws


class TestIterFederatedProjectDirs:
    def test_yields_local_and_federated(self, fed_env):
        main_ws, personal_ws = fed_env
        dirs = list(iter_federated_project_dirs(include_federated=True))
        names = [d.name for d in dirs]
        # Local projects
        assert "🌀paper1" in names
        assert "💻orbit" in names
        # Federated projects
        assert "🤗casa" in names
        assert "🎨musica" in names

    def test_local_first_then_federated(self, fed_env):
        main_ws, personal_ws = fed_env
        dirs = list(iter_federated_project_dirs(include_federated=True))
        # First dirs should be local (under main_ws)
        local_count = sum(1 for d in dirs
                          if str(d).startswith(str(main_ws)))
        # Local should come before federated
        first_fed_idx = next(
            (i for i, d in enumerate(dirs)
             if str(d).startswith(str(personal_ws))),
            len(dirs))
        assert first_fed_idx >= local_count

    def test_no_fed_yields_local_only(self, fed_env):
        dirs = list(iter_federated_project_dirs(include_federated=False))
        names = [d.name for d in dirs]
        assert "💻orbit" in names
        assert "🌀paper1" in names
        assert "🤗casa" not in names
        assert "🎨musica" not in names

    def test_iter_project_dirs_unchanged(self, fed_env):
        """iter_project_dirs should only yield local projects."""
        dirs = list(iter_project_dirs())
        names = [d.name for d in dirs]
        assert "💻orbit" in names
        assert "🤗casa" not in names

    def test_no_federation_config(self, no_fed_env):
        dirs = list(iter_federated_project_dirs(include_federated=True))
        names = [d.name for d in dirs]
        assert names == ["💻app"]


class TestGetFederationEmoji:
    def test_local_project_returns_empty(self, fed_env):
        main_ws, _ = fed_env
        local_dir = main_ws / "💻software" / "💻orbit"
        assert get_federation_emoji(local_dir) == ""

    def test_federated_project_returns_emoji(self, fed_env):
        _, personal_ws = fed_env
        fed_dir = personal_ws / "🤗familia" / "🤗casa"
        assert get_federation_emoji(fed_dir) == "🌿"

    def test_no_federation(self, no_fed_env):
        ws = no_fed_env
        local_dir = ws / "💻software" / "💻app"
        assert get_federation_emoji(local_dir) == ""


class TestIsFederated:
    def test_local_is_not_federated(self, fed_env):
        main_ws, _ = fed_env
        assert not is_federated(main_ws / "💻software" / "💻orbit")

    def test_personal_is_federated(self, fed_env):
        _, personal_ws = fed_env
        assert is_federated(personal_ws / "🤗familia" / "🤗casa")


class TestFederationMissingWorkspace:
    def test_missing_federated_path_skipped(self, tmp_path, monkeypatch):
        """If federated workspace path doesn't exist, it's silently skipped."""
        ws = tmp_path / "main"
        ws.mkdir()
        ws_json = ws / "orbit.json"
        ws_json.write_text(json.dumps({
            "types": {"software": "💻"},
        }, ensure_ascii=False))
        (ws / "💻software" / "💻app").mkdir(parents=True)

        monkeypatch.setattr("core.config.ORBIT_HOME", ws)
        monkeypatch.setattr("core.config._ORBIT_JSON", ws_json)
        monkeypatch.setattr("core.config._FEDERATED_SPACES", [
            {"name": "ghost", "path": str(tmp_path / "nonexistent"), "emoji": "👻"}
        ])

        dirs = list(iter_federated_project_dirs(include_federated=True))
        assert len(dirs) == 1
        assert dirs[0].name == "💻app"
