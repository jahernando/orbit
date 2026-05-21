"""Tests for `views/ring/rings.py` + helper `_ring_table`.

Cubre:
- helper `_format_offset`, `cita_and_suena`, `ring_dt`
- viewer behaviour: sin ring.json → mensaje;
  con ring.json → tabla; filtrado por día-de-alarma; secciones por día.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path


# ── helper _ring_table ──────────────────────────────────────────────────


class TestFormatOffset:
    def test_minutes(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(5) == "-5m"
        assert _format_offset(10) == "-10m"

    def test_hours_exact(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(60) == "-1h"
        assert _format_offset(120) == "-2h"

    def test_days_exact(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(1440) == "-1d"
        assert _format_offset(7200) == "-5d"

    def test_non_exact_falls_to_minutes(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(75) == "-75m"

    def test_negative_alarm_after(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(-5) == "+5m"

    def test_zero(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(0) == "0m"

    def test_none(self):
        from views.ring._ring_table import _format_offset
        assert _format_offset(None) == ""


class TestCitaAndSuena:
    def test_same_day(self):
        from views.ring._ring_table import cita_and_suena
        ring_dt = datetime(2026, 5, 19, 12, 55)
        cita, suena = cita_and_suena("2026-05-19T13:00:00", 5, ring_dt)
        assert cita == "13:00"
        assert suena == "12:55 (-5m)"

    def test_alarm_one_day_before(self):
        from views.ring._ring_table import cita_and_suena
        ring_dt = datetime(2026, 5, 21, 9, 0)
        cita, suena = cita_and_suena("2026-05-22T09:00:00", 1440, ring_dt)
        assert cita == "22/05 09:00"
        assert suena == "09:00 (-1d)"

    def test_bad_due_iso(self):
        from views.ring._ring_table import cita_and_suena
        ring_dt = datetime(2026, 5, 19, 12, 0)
        assert cita_and_suena("nope", 5, ring_dt) == ("?", "?")


class TestRingDt:
    def test_basic(self):
        from views.ring._ring_table import ring_dt
        item = {"due_iso": "2026-05-19T13:00:00", "alarm_minutes": 5}
        assert ring_dt(item) == datetime(2026, 5, 19, 12, 55)

    def test_alarm_minutes_missing_treated_as_zero(self):
        from views.ring._ring_table import ring_dt
        item = {"due_iso": "2026-05-19T13:00:00"}
        assert ring_dt(item) == datetime(2026, 5, 19, 13, 0)

    def test_bad_due_iso_returns_none(self):
        from views.ring._ring_table import ring_dt
        assert ring_dt({"due_iso": "bad", "alarm_minutes": 5}) is None
        assert ring_dt({}) is None


# ── viewer ──────────────────────────────────────────────────────────────


def _write_ring_json(tmp_path: Path, items: list, **extras) -> None:
    (tmp_path / ".reminders").mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-05-19T18:00:00",
        "window_start": "2026-05-19",
        "window_end":   "2026-05-26",
        "enabled":      True,
        "list":         "test-list",
        "items":        items,
    }
    payload.update(extras)
    (tmp_path / ".reminders" / "ring.json").write_text(json.dumps(payload))


class TestRingsViewer:
    def test_no_ring_json_message(self, orbit_env):
        from views.ring import rings
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "Sin `ring.json`" in text

    def test_no_items_at_all(self, orbit_env):
        from views.ring import rings
        _write_ring_json(orbit_env["tmp"], [])
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "Sin alarmas programadas" in text
        # Hoy aparece como sección aunque esté vacía
        assert "## 🔔 Hoy" in text
        # Próximos días NO aparece si no hay items
        assert "## 🔔 Próximos días" not in text

    def test_item_today_renders_in_today_section(self, orbit_env):
        from views.ring import rings
        today = date.today()
        due = datetime.combine(today, datetime.min.time()).replace(hour=13)
        _write_ring_json(orbit_env["tmp"], [{
            "orbit_id":      "abc",
            "project":       "💻testproj",
            "kind":          "event",
            "title":         "comida con Xabi",
            "due_iso":       due.isoformat(),
            "alarm_minutes": 5,
            "list":          "test-list",
        }])
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        # Counter cuenta el item
        assert "🔔 Hoy: 1" in text
        # Item visible
        assert "comida con Xabi" in text
        assert "13:00" in text
        assert "(-5m)" in text
        # Bajo "Hoy", no bajo "Próximos días"
        hoy_idx = text.find("## 🔔 Hoy")
        prox_idx = text.find("## 🔔 Próximos días")
        comida_idx = text.find("comida con Xabi")
        assert hoy_idx >= 0
        assert hoy_idx < comida_idx
        assert prox_idx == -1 or comida_idx < prox_idx

    def test_item_tomorrow_with_one_day_alarm_appears_today(self, orbit_env):
        """alarm_minutes=1440 hace que un item de mañana suene HOY → debe ir a Hoy."""
        from views.ring import rings
        tomorrow = date.today() + timedelta(days=1)
        due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=9)
        _write_ring_json(orbit_env["tmp"], [{
            "orbit_id":      "abc",
            "project":       "💻testproj",
            "kind":          "milestone",
            "title":         "deadline",
            "due_iso":       due.isoformat(),
            "alarm_minutes": 1440,
            "list":          "test-list",
        }])
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "deadline" in text
        assert "(-1d)" in text
        assert tomorrow.strftime("%d/%m") in text  # cita muestra día explícito
        # Cae en Hoy (porque el ring suena hoy aunque cita sea mañana)
        hoy_idx = text.find("## 🔔 Hoy")
        deadline_idx = text.find("deadline")
        assert hoy_idx >= 0 and hoy_idx < deadline_idx

    def test_item_tomorrow_with_5m_alarm_goes_to_proximos(self, orbit_env):
        """alarm a 5m de un item de mañana → sección Próximos días, no Hoy."""
        from views.ring import rings
        tomorrow = date.today() + timedelta(days=1)
        due = datetime.combine(tomorrow, datetime.min.time()).replace(hour=9)
        _write_ring_json(orbit_env["tmp"], [{
            "orbit_id":      "abc",
            "project":       "💻testproj",
            "kind":          "task",
            "title":         "tarea mañana",
            "due_iso":       due.isoformat(),
            "alarm_minutes": 5,
            "list":          "test-list",
        }])
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "tarea mañana" in text
        # Counter
        assert "Próximos 7d: 1" in text
        # Sección Próximos días presente, con sub-header del día
        assert "## 🔔 Próximos días" in text
        assert f"### {tomorrow.isoformat()}" in text
        prox_idx = text.find("## 🔔 Próximos días")
        tarea_idx = text.find("tarea mañana")
        assert prox_idx >= 0 and prox_idx < tarea_idx

    def test_groups_by_ring_day(self, orbit_env):
        from views.ring import rings
        today = date.today()
        d2 = today + timedelta(days=2)
        items = [
            {
                "orbit_id":      "a",
                "project":       "💻testproj",
                "kind":          "event",
                "title":         "hoy",
                "due_iso":       datetime.combine(
                    today, datetime.min.time()).replace(hour=13).isoformat(),
                "alarm_minutes": 5,
                "list":          "test-list",
            },
            {
                "orbit_id":      "b",
                "project":       "💻testproj",
                "kind":          "event",
                "title":         "pasado mañana",
                "due_iso":       datetime.combine(
                    d2, datetime.min.time()).replace(hour=10).isoformat(),
                "alarm_minutes": 5,
                "list":          "test-list",
            },
        ]
        _write_ring_json(orbit_env["tmp"], items)
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        # Sub-header del día d2 bajo Próximos días
        assert f"### {d2.isoformat()}" in text
        # Item de hoy en Hoy, item futuro en Próximos
        assert "hoy" in text
        assert "pasado mañana" in text
        assert "🔔 Hoy: 1" in text
        assert "Próximos 7d: 1" in text

    def test_ring_in_past_excluded(self, orbit_env):
        """Item cuyo ring ya pasó NO aparece en rings.md."""
        from views.ring import rings
        yesterday = date.today() - timedelta(days=1)
        due = datetime.combine(yesterday, datetime.min.time()).replace(hour=9)
        _write_ring_json(orbit_env["tmp"], [{
            "orbit_id":      "old",
            "project":       "💻testproj",
            "kind":          "task",
            "title":         "antiguo",
            "due_iso":       due.isoformat(),
            "alarm_minutes": 5,
            "list":          "test-list",
        }])
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "antiguo" not in text
        assert "Sin alarmas programadas" in text

    def test_disabled_ring_shows_in_header(self, orbit_env):
        from views.ring import rings
        _write_ring_json(orbit_env["tmp"], [], enabled=False)
        out = orbit_env["tmp"] / "rings.md"
        rings.generate(out)
        text = out.read_text()
        assert "ring deshabilitado" in text
