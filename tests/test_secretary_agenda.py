"""tests/test_secretary_agenda.py — tests del nuevo viewer hot único.

Cubre el comportamiento decidido en [[project-orbit-dashboard-refactor]]:
- Counter telegráfico adaptativo (categorías con N=0 omitidas; línea de hitos
  desaparece si N=0; reminders excluidos del counter).
- Tabla de Hoy mezcla citas + ⚠️ vencidas (cap 10) + ⏩ followups<=today.
- Bloque "Próximos días" con tablas por día y ⏩ inline por día.
- Smoke de `generate()` sobre workspace vacío.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from views.secretary import agenda as sec_agenda


def _base_name(name: str) -> str:
    """Strip leading emoji-ish codepoints to get the base name (mismo patrón
    que `test_panel._base_name`)."""
    i = 0
    while i < len(name) and (ord(name[i]) > 127 or name[i] in "️‍"):
        i += 1
    return name[i:]


def _make_project(type_dir: Path, name="💻test-project", agenda_extra=""):
    base = _base_name(name)
    proj = type_dir / name
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{base}-project.md").write_text(
        f"# {name}\n- Tipo: 💻 Software\n- Estado: [auto]\n- Prioridad: media\n"
    )
    (proj / f"{base}-logbook.md").write_text(f"# Logbook — {name}\n")
    (proj / f"{base}-agenda.md").write_text(f"# Agenda — {name}\n\n{agenda_extra}")
    (proj / "notes").mkdir(exist_ok=True)
    return proj


@pytest.fixture()
def agenda_env(tmp_path, monkeypatch):
    type_dir = tmp_path / "💻software"
    type_dir.mkdir()
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.config._ORBIT_JSON", tmp_path / "orbit.json")
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    return {"tmp": tmp_path, "type_dir": type_dir}


# ── Collectors ────────────────────────────────────────────────────────────────

class TestCollectOverdue:

    def test_includes_pending_with_past_date(self, agenda_env):
        today = date.today()
        past = (today - timedelta(days=2)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Old task ({past})\n",
        )
        out = sec_agenda._collect_overdue(today)
        assert len(out) == 1
        assert out[0][1]["desc"] == "Old task"

    def test_excludes_today_and_future(self, agenda_env):
        today = date.today()
        future = (today + timedelta(days=1)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## ✅ Tareas\n"
                f"- [ ] Today task ({today.isoformat()})\n"
                f"- [ ] Future task ({future})\n"
            ),
        )
        assert sec_agenda._collect_overdue(today) == []

    def test_excludes_done_and_cancelled(self, agenda_env):
        today = date.today()
        past = (today - timedelta(days=3)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## ✅ Tareas\n"
                f"- [x] Done ({past})\n"
                f"- [-] Cancelled ({past})\n"
            ),
        )
        assert sec_agenda._collect_overdue(today) == []

    def test_excludes_recurring(self, agenda_env):
        today = date.today()
        past = (today - timedelta(days=1)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Daily X ({past}) [🔄daily]\n",
        )
        assert sec_agenda._collect_overdue(today) == []

    def test_ordered_oldest_first(self, agenda_env):
        today = date.today()
        d1 = (today - timedelta(days=5)).isoformat()
        d2 = (today - timedelta(days=1)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## ✅ Tareas\n"
                f"- [ ] Recent ({d2})\n"
                f"- [ ] Ancient ({d1})\n"
            ),
        )
        out = sec_agenda._collect_overdue(today)
        assert [t["desc"] for _, t in out] == ["Ancient", "Recent"]


class TestCollectFollowups:
    """⏩ followups (body lines) son la fuente única de "por triar" tras F5
    (el eje ``ff`` de cabecera fue retirado)."""

    def test_includes_followup_in_range_on_task(self, agenda_env):
        today = date.today()
        d = (today + timedelta(days=2)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Inscripción\n    ⏩ {d}\n",
        )
        out = sec_agenda._collect_followups_in_range(
            (today + timedelta(days=1)).isoformat(),
            (today + timedelta(days=7)).isoformat(),
        )
        assert len(out) == 1
        _proj, kind, item, fup = out[0]
        assert kind == "tasks"
        assert fup["date"] == d
        assert item["desc"] == "Inscripción"

    def test_followup_on_event_carries_desc(self, agenda_env):
        today = date.today()
        d = (today + timedelta(days=2)).isoformat()
        ev_date = (today + timedelta(days=30)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## 📅 Eventos\n{ev_date} — Workshop\n    ⏩ {d} deadline inscripción\n",
        )
        out = sec_agenda._collect_followups_in_range(
            (today + timedelta(days=1)).isoformat(),
            (today + timedelta(days=7)).isoformat(),
        )
        assert len(out) == 1
        _proj, kind, _item, fup = out[0]
        assert kind == "events"
        assert fup["desc"] == "deadline inscripción"

    def test_excludes_done_and_out_of_range(self, agenda_env):
        today = date.today()
        in_range = (today + timedelta(days=2)).isoformat()
        far      = (today + timedelta(days=99)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## ✅ Tareas\n"
                f"- [x] Done\n    ⏩ {in_range}\n"
                f"- [ ] Live\n    ⏩ {far}\n"
            ),
        )
        out = sec_agenda._collect_followups_in_range(
            date.min.isoformat(), (today + timedelta(days=7)).isoformat(),
        )
        assert out == []   # done excluded; live one is out of the 7d window

    def test_excludes_someday(self, agenda_env):
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra="## ✅ Tareas\n- [ ] Maybe\n    ⏩ someday\n",
        )
        out = sec_agenda._collect_followups_in_range(
            date.min.isoformat(), (today + timedelta(days=30)).isoformat(),
        )
        assert out == []


class TestFollowupSurfacing:
    """Followups son la fuente única que alimenta el contador y la tabla de Hoy."""

    def test_counter_counts_followups_as_por_triar(self):
        followups = [(None, "events", {"desc": "x"}, {"date": "2026-01-01"})]
        out = sec_agenda._counter_lines([], [], 0, followups_today=followups)
        assert out == ["> 🗓 Hoy: ⏩1 por triar"]

    def test_today_block_renders_followup_row(self, agenda_env):
        today = date.today()
        d = today.isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Inscripción\n    ⏩ {d} ojo\n",
        )
        followups = sec_agenda._collect_followups_in_range(date.min.isoformat(), d)
        block = sec_agenda._today_block([], [], followups)
        # col1 = tipo (☐ task), col2 = ⏩.
        fup_rows = [l for l in block if "| ⏩ |" in l]
        assert len(fup_rows) == 1
        assert fup_rows[0].startswith("| ☐ |")
        assert "Inscripción" in fup_rows[0]
        assert "ojo" in fup_rows[0]


class TestCountMilestonesWindow:

    def test_counts_within_30d(self, agenda_env):
        today = date.today()
        inside = (today + timedelta(days=29)).isoformat()
        outside = (today + timedelta(days=31)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 🏁 Hitos\n"
                f"- [ ] Soon ({inside})\n"
                f"- [ ] Far ({outside})\n"
            ),
        )
        assert sec_agenda._count_milestones_window(today) == 1


# ── Counter ───────────────────────────────────────────────────────────────────

class TestCounterLines:

    def test_all_zero_shows_sin_compromisos(self):
        out = sec_agenda._counter_lines([], [], 0)
        assert out == ["> 🗓 Hoy: sin compromisos"]

    def test_omits_zero_categories(self):
        today_items = [("events", {}, None, "")]
        out = sec_agenda._counter_lines(today_items, [], 0)
        assert out == ["> 🗓 Hoy: 📅1 eventos"]

    def test_includes_all_categories_when_present(self):
        today_items = [
            ("events", {}, None, ""), ("events", {}, None, ""),
            ("tasks", {}, None, ""),
        ]
        overdue = [(None, {"desc": "x", "date": "2026-01-01"})]
        followups = [(None, "tasks", {"desc": "y"}, {"date": "2026-01-01"})]
        out = sec_agenda._counter_lines(today_items, overdue, 0,
                                        followups_today=followups)
        assert out == [
            "> 🗓 Hoy: 📅2 eventos · ✅1 tareas · ⚠️1 vencidas · ⏩1 por triar"
        ]

    def test_milestones_line_omitted_when_zero(self):
        out = sec_agenda._counter_lines([], [], 0)
        assert all("hitos" not in line for line in out)

    def test_milestones_line_shown_when_positive(self):
        out = sec_agenda._counter_lines([], [], 3)
        assert out[-1] == (
            f"> 🏁 Hitos: 3 próximos {sec_agenda.MILESTONES_WINDOW} días "
            "· [detalle](hitos.md)"
        )

    def test_milestones_line_includes_overdue(self):
        out = sec_agenda._counter_lines([], [], 3, n_overdue_ms=2)
        assert out[-1] == (
            f"> 🏁 Hitos: ⚠️2 vencidos · 3 próximos "
            f"{sec_agenda.MILESTONES_WINDOW} días · [detalle](hitos.md)"
        )

    def test_milestones_line_only_overdue(self):
        out = sec_agenda._counter_lines([], [], 0, n_overdue_ms=2)
        assert out[-1] == "> 🏁 Hitos: ⚠️2 vencidos · [detalle](hitos.md)"

    def test_milestones_line_omitted_when_both_zero(self):
        out = sec_agenda._counter_lines([], [], 0, n_overdue_ms=0)
        assert all("Hitos" not in line for line in out)

    def test_ring_line_omitted_when_zero(self):
        out = sec_agenda._counter_lines([], [], 0, ring_counts=(0, 0))
        assert all("Alarmas" not in line for line in out)

    def test_ring_line_today_only(self):
        out = sec_agenda._counter_lines([], [], 0, ring_counts=(2, 0))
        assert out[-1] == "> 🔔 Alarmas: 2 hoy · [detalle](../ring/rings.md)"

    def test_ring_line_next_only(self):
        out = sec_agenda._counter_lines([], [], 0, ring_counts=(0, 3))
        assert out[-1] == (
            f"> 🔔 Alarmas: 3 próximos {sec_agenda.NEXT_DAYS_WINDOW} días "
            "· [detalle](../ring/rings.md)"
        )

    def test_ring_line_today_and_next(self):
        out = sec_agenda._counter_lines([], [], 0, ring_counts=(2, 3))
        assert out[-1] == (
            f"> 🔔 Alarmas: 2 hoy · 3 próximos {sec_agenda.NEXT_DAYS_WINDOW} días "
            "· [detalle](../ring/rings.md)"
        )

    def test_count_rings_truth_heuristic(self):
        today = date(2026, 6, 4)
        end = today + timedelta(days=sec_agenda.NEXT_DAYS_WINDOW)
        today_items = [
            ("reminders", {}, None, ""),             # reminder → siempre
            ("tasks", {"time": "10:00"}, None, ""),  # con hora → sí
            ("tasks", {}, None, ""),                 # sin hora → no
            ("events", {"time": "12:00"}, None, ""), # con hora → sí
        ]
        by_day = {
            (today + timedelta(days=2)).isoformat(): [
                ("events", {"time": "09:00"}, None, ""),
                ("events", {}, None, ""),            # sin hora → no
            ],
            (today + timedelta(days=99)).isoformat(): [  # fuera de ventana
                ("reminders", {}, None, ""),
            ],
        }
        n_today, n_next = sec_agenda._count_rings(today_items, by_day, today, end)
        assert n_today == 3
        assert n_next == 1

    def test_reminders_excluded_from_counter(self):
        today_items = [("reminders", {}, None, "")]
        out = sec_agenda._counter_lines(today_items, [], 0)
        assert out == ["> 🗓 Hoy: sin compromisos"]

    def test_milestones_today_not_in_today_line(self):
        """Milestones de hoy aparecen en la tabla con 🏁 pero NO en el counter
        (los hitos viven en la línea "Próximos 30 días")."""
        today_items = [("milestones", {}, None, "")]
        out = sec_agenda._counter_lines(today_items, [], 0)
        assert out == ["> 🗓 Hoy: sin compromisos"]


# ── Overdue cap en tabla de Hoy ───────────────────────────────────────────────

class TestOverdueCap:

    def test_overflow_emits_summary_row(self, agenda_env, monkeypatch):
        # 12 overdue → 10 mostradas + 1 fila resumen "…y 2 más"
        today = date.today()
        past = (today - timedelta(days=1)).isoformat()
        lines = "\n".join(f"- [ ] Old {i} ({past})" for i in range(12))
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n{lines}\n",
        )
        overdue = sec_agenda._collect_overdue(today)
        block = sec_agenda._today_block([], overdue)
        # Header + 10 filas vencidas (☐ tipo, ⚠️ estado) + 1 resumen = 12 líneas
        warn_rows = [l for l in block if "| ⚠️ |" in l]
        assert len(warn_rows) == 11
        assert any("…y 2 más vencidas" in l for l in warn_rows)


# ── Smoke de generate() ───────────────────────────────────────────────────────

class TestGenerate:

    def test_empty_workspace_writes_minimal_file(self, agenda_env):
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "secretary.agenda" in text  # banner
        assert "🗓 Hoy: sin compromisos" in text
        assert "## 📅 Hoy" in text
        assert "*Sin citas para hoy.*" in text
        assert "## 📅 Próximos días" not in text

    def test_with_today_event_renders_counter_and_row(self, agenda_env):
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 📅 Eventos\n"
                f"{today.isoformat()} — Reunión ⏰10:00-11:00\n"
            ),
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "📅1 eventos" in text
        assert "Reunión" in text
        assert "10:00" in text

    def test_overdue_arrastrada_a_hoy_con_warning(self, agenda_env):
        today = date.today()
        past = (today - timedelta(days=2)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Old task ({past})\n",
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "⚠️1 vencidas" in text
        assert "| ⚠️ |" in text
        assert f"(📅{past})" in text

    def test_followup_today_aparece_con_triaje(self, agenda_env):
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Decidir X\n    ⏩ {today.isoformat()}\n",
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "⏩1 por triar" in text
        assert "| ⏩ |" in text
        assert "Decidir X" in text

    def test_followup_future_aparece_en_proximos_dias(self, agenda_env):
        today = date.today()
        d = (today + timedelta(days=2)).isoformat()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Triar futuro\n    ⏩ {d}\n",
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        # No aparece en hoy
        assert "⏩1 por triar" not in text
        # Aparece en próximos días con ⏩ en la tabla del día
        assert "## 📅 Próximos días" in text
        assert f"### {d}" in text
        assert "| ⏩ |" in text
        assert "Triar futuro" in text


class TestBellColumn:
    """Columna 🔔 en la tabla de citas. Display-only: reminders siempre,
    task/ms/event si tienen `time` (regla en `bell_cell`). La cabecera
    no lleva 🔔 — el icono sólo aparece en filas con alarma."""

    def test_event_with_time_shows_bell(self, agenda_env):
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 📅 Eventos\n"
                f"{today.isoformat()} — Reunión ⏰10:00 🔔5m\n"
            ),
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        # Fila con bell. La columna está justo después del kind-emoji.
        assert "| 📅 | 🔔 |" in text

    def test_event_with_time_no_ring_still_shows_bell(self, agenda_env):
        """Display-only: evento con hora pero sin ring explícito → 🔔."""
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 📅 Eventos\n"
                f"{today.isoformat()} — Sin ring explícito ⏰10:00\n"
            ),
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "| 📅 | 🔔 |" in text

    def test_reminder_always_shows_bell(self, agenda_env):
        """Reminders siempre 🔔 (reminder == ring por construcción)."""
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 💬 Recordatorios\n"
                f"- Llamar ({today.isoformat()}) ⏰15:00\n"
            ),
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        assert "| 💬 | 🔔 |" in text

    def test_header_has_no_bell(self, agenda_env):
        """Cabecera de la tabla no lleva 🔔; sólo aparece en filas."""
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=(
                "## 📅 Eventos\n"
                f"{today.isoformat()} — Reunión ⏰10:00 🔔5m\n"
            ),
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        # La línea de header NO tiene 🔔.
        assert "| | | | Inicio | Fin | Descripción | Proyecto |" in text
        assert "| 🔔 | | Inicio" not in text

    def test_followup_rows_aligned_state_in_col2(self, agenda_env):
        """Filas por-triar: col1=tipo, col2=⏩ (la col estado), 7 cols alineadas."""
        today = date.today()
        _make_project(
            agenda_env["type_dir"],
            agenda_extra=f"## ✅ Tareas\n- [ ] Decidir X\n    ⏩ {today.isoformat()}\n",
        )
        out = agenda_env["tmp"] / "agenda.md"
        sec_agenda.generate(out)
        text = out.read_text()
        # ⏩ row: col1=tipo (☐), col2=⏩, 7 columnas.
        # Cuenta los pipes en la línea de la fila para confirmar 8 (= 7 cols).
        for line in text.splitlines():
            if "| ⏩ |" in line:
                assert line.startswith("| ☐ |"), f"col1 no es tipo: {line!r}"
                assert line.count("|") == 8, f"row mal alineada: {line!r}"
                break
        else:
            pytest.fail("no encontré la fila ⏩")
