"""test_config.py — unit tests for configurable project types.

Covers:
  - get_type_map:    loads types, includes accent variants
  - get_type_emojis: returns tuple of emojis
  - get_type_label:  returns labels with accents
  - run_type_list:   prints all types
  - run_type_add:    adds new type, rejects duplicates, rejects duplicate emoji
  - run_type_drop:   removes type, rejects if projects exist
"""

import json
import pytest
from pathlib import Path

from core.config import (
    get_type_map, get_type_emojis, get_type_label,
    run_type_list, run_type_add, run_type_drop,
    normalize as _normalize,
)


@pytest.fixture
def config_env(tmp_path, monkeypatch):
    """Isolated config env with orbit.json."""
    orbit_json = tmp_path / "orbit.json"
    projects_dir = tmp_path / "🚀proyectos"
    projects_dir.mkdir()

    types = {
        "software": "💻",
        "investigacion": "🌀",
        "personal": "🌿",
    }
    orbit_json.write_text(json.dumps({"types": types}, ensure_ascii=False))

    monkeypatch.setattr("core.config._ORBIT_JSON", orbit_json)
    monkeypatch.setattr("core.config.PROJECTS_DIR", projects_dir)

    return {"orbit_json": orbit_json, "projects_dir": projects_dir}


class TestNormalize:

    def test_strips_accents(self):
        assert _normalize("investigación") == "investigacion"

    def test_lowercase(self):
        assert _normalize("Software") == "software"


class TestGetTypeMap:

    def test_includes_base_types(self, config_env):
        m = get_type_map()
        assert m["software"] == "💻"
        assert m["investigacion"] == "🌀"

    def test_includes_accent_variants(self, config_env):
        m = get_type_map()
        assert m.get("investigación") == "🌀"


class TestGetTypeEmojis:

    def test_returns_tuple(self, config_env):
        emojis = get_type_emojis()
        assert isinstance(emojis, tuple)
        assert "💻" in emojis
        assert "🌀" in emojis


class TestGetTypeLabel:

    def test_returns_capitalized_labels(self, config_env):
        labels = get_type_label()
        assert labels["software"] == "Software"

    def test_prefers_accented_label(self, config_env):
        labels = get_type_label()
        assert labels["investigacion"] == "Investigación"


class TestRunTypeList:

    def test_lists_types(self, config_env, capsys):
        rc = run_type_list()
        assert rc == 0
        out = capsys.readouterr().out
        assert "software" in out
        assert "💻" in out


class TestRunTypeAdd:

    def test_adds_new_type(self, config_env, capsys):
        rc = run_type_add("viajes", "✈️")
        assert rc == 0
        out = capsys.readouterr().out
        assert "✓" in out

        # Verify in orbit.json
        config = json.loads(config_env["orbit_json"].read_text())
        assert config["types"]["viajes"] == "✈️"

    def test_rejects_existing_type(self, config_env, capsys):
        rc = run_type_add("software", "🔧")
        assert rc == 1
        assert "ya existe" in capsys.readouterr().out

    def test_rejects_duplicate_emoji(self, config_env, capsys):
        rc = run_type_add("programacion", "💻")
        assert rc == 1
        assert "ya está en uso" in capsys.readouterr().out


class TestRunTypeDrop:

    def test_drops_type(self, config_env, capsys):
        rc = run_type_drop("personal")
        assert rc == 0
        config = json.loads(config_env["orbit_json"].read_text())
        assert "personal" not in config["types"]

    def test_rejects_nonexistent(self, config_env, capsys):
        rc = run_type_drop("fantasma")
        assert rc == 1
        assert "no existe" in capsys.readouterr().out

    def test_rejects_if_projects_exist(self, config_env, capsys):
        # Create a project with the 💻 emoji
        proj = config_env["projects_dir"] / "💻myproj"
        proj.mkdir()
        rc = run_type_drop("software")
        assert rc == 1
        assert "No se puede eliminar" in capsys.readouterr().out
