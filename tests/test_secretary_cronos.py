"""tests/test_secretary_cronos.py — viewer cold `cronos.md`.

Cubre:
- `_crono_link_md`: link relativo desde 📊panel/secretary/; fuera de
  ORBIT_HOME → texto plano.
- `generate()`: la columna Cronograma enlaza el `cronos/crono-*.md` de
  origen; smoke sin cronogramas.
"""

from pathlib import Path

import pytest

from views.secretary import cronos as sec_cronos


def _base_name(name: str) -> str:
    i = 0
    while i < len(name) and (ord(name[i]) > 127 or name[i] in "️‍"):
        i += 1
    return name[i:]


def _make_project(type_dir: Path, name="💻test-project", cronos=None):
    base = _base_name(name)
    proj = type_dir / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (proj / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n")
    (proj / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n")
    (proj / "notes").mkdir(exist_ok=True)
    if cronos:
        cdir = proj / "cronos"
        cdir.mkdir(exist_ok=True)
        for slug, text in cronos.items():
            (cdir / f"crono-{slug}.md").write_text(text)
    return proj


@pytest.fixture()
def cronos_env(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return {"tmp": tmp_path, "type_dir": type_dir}


_CRONO_OPEN = (
    "# Cronograma: Plan notas\n"
    "deadline: 2026-06-12\n\n"
    "- [x] 1. t1\n"
    "- [ ] 2. t2\n"
)


class TestCronoLinkMd:

    def test_link_relative_to_orbit_home(self, cronos_env):
        proj = _make_project(cronos_env["type_dir"],
                             cronos={"plan-notas": _CRONO_OPEN})
        f = proj / "cronos" / "crono-plan-notas.md"
        assert sec_cronos._crono_link_md(f, "Plan notas") == (
            "[Plan notas](../../💻software/💻test-project/cronos/"
            "crono-plan-notas.md)"
        )

    def test_outside_orbit_home_plain_text(self, cronos_env, tmp_path):
        other = tmp_path.parent / "otro-vault" / "crono-x.md"
        assert sec_cronos._crono_link_md(other, "Plan X") == "Plan X"


class TestGenerate:

    def test_crono_column_links_file(self, cronos_env, tmp_path):
        _make_project(cronos_env["type_dir"], cronos={"plan-notas": _CRONO_OPEN})
        out = tmp_path / "cronos.md"
        sec_cronos.generate(out)
        content = out.read_text()
        assert "[Plan notas](../../💻software/💻test-project/cronos/" \
               "crono-plan-notas.md)" in content
        assert "1/2 (50%)" in content

    def test_empty_smoke(self, cronos_env, tmp_path):
        out = tmp_path / "cronos.md"
        sec_cronos.generate(out)
        assert "(sin cronogramas abiertos)" in out.read_text()
