"""tests/test_secretary_hitos.py — viewer cold `hitos.md`.

Cubre:
- `_collect_milestones_window`: ventana 30d, pending-only, orden por fecha.
- `_fecha_cell`: formato MM-DD + días, ⚠️ si ≤3d.
- `_crono_cell`: vínculo por nombre con cronograma; ISO date NO asocia.
- `generate()`: tabla con filas, '—' sin crono, smoke vacío.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from views.secretary import agenda as sec_agenda
from views.secretary import hitos as sec_hitos


def _base_name(name: str) -> str:
    i = 0
    while i < len(name) and (ord(name[i]) > 127 or name[i] in "️‍"):
        i += 1
    return name[i:]


def _make_project(type_dir: Path, name="💻test-project", agenda_extra="",
                  cronos=None):
    base = _base_name(name)
    proj = type_dir / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (proj / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n")
    (proj / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n{agenda_extra}")
    (proj / "notes").mkdir(exist_ok=True)
    if cronos:
        cdir = proj / "cronos"
        cdir.mkdir(exist_ok=True)
        for slug, text in cronos.items():
            (cdir / f"crono-{slug}.md").write_text(text)
    return proj


@pytest.fixture()
def hitos_env(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return {"tmp": tmp_path, "type_dir": type_dir}


# ── _collect_milestones_window ──────────────────────────────────────────────

class TestCollectMilestonesWindow:

    def test_window_pending_only_sorted(self, hitos_env):
        today = date.today()
        d10 = (today + timedelta(days=10)).isoformat()
        d5 = (today + timedelta(days=5)).isoformat()
        far = (today + timedelta(days=31)).isoformat()
        _make_project(
            hitos_env["type_dir"],
            agenda_extra=(
                "## 🏁 Hitos\n"
                f"- [ ] B late ({d10})\n"
                f"- [ ] A early ({d5})\n"
                f"- [x] Done ({d5})\n"
                f"- [ ] Far ({far})\n"
            ),
        )
        out = sec_agenda._collect_milestones_window(today)
        descs = [m["desc"] for _, m in out]
        assert descs == ["A early", "B late"]

    def test_overdue_collector(self, hitos_env):
        today = date.today()
        past = (today - timedelta(days=4)).isoformat()
        future = (today + timedelta(days=4)).isoformat()
        _make_project(
            hitos_env["type_dir"],
            agenda_extra=(
                "## 🏁 Hitos\n"
                f"- [ ] Late ({past})\n"
                f"- [x] Done late ({past})\n"
                f"- [ ] Future ({future})\n"
            ),
        )
        out = sec_agenda._collect_overdue_milestones(today)
        assert [m["desc"] for _, m in out] == ["Late"]


# ── _fecha_cell ─────────────────────────────────────────────────────────────

class TestFechaCell:

    def test_far_no_warning(self):
        today = date(2026, 6, 1)
        assert sec_hitos._fecha_cell(date(2026, 6, 12), today) == "06-12 (11d)"

    def test_near_no_warning(self):
        # Inminente pero no vencido: sin ⚠️ (⚠️ = solo vencido).
        today = date(2026, 6, 1)
        assert sec_hitos._fecha_cell(date(2026, 6, 3), today) == "06-03 (2d)"

    def test_today_no_warning(self):
        today = date(2026, 6, 1)
        assert sec_hitos._fecha_cell(today, today) == "06-01 (0d)"

    def test_overdue_warning_in_fecha(self):
        today = date(2026, 6, 8)
        # Vencido: ⚠️ en la columna fecha.
        assert sec_hitos._fecha_cell(date(2026, 6, 1), today) == "⚠️ 06-01 (vencido 7d)"


# ── _crono_cell ─────────────────────────────────────────────────────────────

_CRONO_BY_NAME = (
    "# Cronograma: Plan notas\n"
    "deadline: Entregar notas\n\n"
    "- [x] 1. t1\n"
    "- [ ] 2. t2\n"
)

_CRONO_BY_ISO = (
    "# Cronograma: Plan iso\n"
    "deadline: 2026-06-12\n\n"
    "- [ ] 1. t1\n"
    "- [ ] 2. t2\n"
)


class TestCronoCell:

    def test_links_crono_by_name(self, hitos_env):
        proj = _make_project(
            hitos_env["type_dir"],
            cronos={"plan-notas": _CRONO_BY_NAME},
        )
        cell = sec_hitos._crono_cell(proj, "Entregar notas")
        assert "Plan notas" in cell
        assert "1/2" in cell
        assert "█" in cell and "░" in cell

    def test_iso_deadline_not_linked(self, hitos_env):
        proj = _make_project(
            hitos_env["type_dir"],
            cronos={"plan-iso": _CRONO_BY_ISO},
        )
        # Aunque la fecha coincida, un deadline ISO no se asocia por nombre.
        assert sec_hitos._crono_cell(proj, "Entregar notas") == ""

    def test_no_cronos_dir(self, hitos_env):
        proj = _make_project(hitos_env["type_dir"])
        assert sec_hitos._crono_cell(proj, "Entregar notas") == ""


# ── generate ────────────────────────────────────────────────────────────────

class TestGenerate:

    def test_empty_workspace(self, hitos_env, tmp_path):
        out = tmp_path / "hitos.md"
        sec_hitos.generate(out)
        text = out.read_text()
        assert "Hitos" in text
        assert "sin hitos" in text

    def test_overdue_row_marked(self, hitos_env):
        today = date.today()
        past = (today - timedelta(days=5)).isoformat()
        soon = (today + timedelta(days=5)).isoformat()
        _make_project(
            hitos_env["type_dir"],
            agenda_extra=(
                "## 🏁 Hitos\n"
                f"- [ ] Vencido ({past})\n"
                f"- [ ] Pronto ({soon})\n"
            ),
        )
        out = hitos_env["tmp"] / "hitos.md"
        sec_hitos.generate(out)
        rows = [l for l in out.read_text().splitlines() if "|" in l and "(" in l]
        vencido_row = [l for l in rows if "Vencido" in l][0]
        pronto_row = [l for l in rows if "Pronto" in l][0]
        # col1 siempre 🏁 (tipo); el estado vencido va en la fecha con ⚠️.
        assert vencido_row.startswith("| 🏁 |")
        assert pronto_row.startswith("| 🏁 |")
        assert "⚠️" in vencido_row and "vencido 5d" in vencido_row
        assert "⚠️" not in pronto_row
        # Vencido va antes que próximo (orden por fecha asc).
        assert rows.index(vencido_row) < rows.index(pronto_row)

    def test_table_with_crono_and_dash(self, hitos_env):
        today = date.today()
        d8 = (today + timedelta(days=8)).isoformat()
        d9 = (today + timedelta(days=9)).isoformat()
        _make_project(
            hitos_env["type_dir"],
            agenda_extra=(
                "## 🏁 Hitos\n"
                f"- [ ] Entregar notas ({d8})\n"
                f"- [ ] Defensa ({d9})\n"
            ),
            cronos={"plan-notas": _CRONO_BY_NAME},
        )
        out = hitos_env["tmp"] / "hitos.md"
        sec_hitos.generate(out)
        text = out.read_text()
        assert "| 🏁 |" in text
        assert "Entregar notas" in text and "Defensa" in text
        assert "Plan notas" in text          # hito con crono
        # La fila de Defensa no tiene crono → celda '—'
        defensa_row = [l for l in text.splitlines() if "Defensa" in l][0]
        assert "—" in defensa_row
