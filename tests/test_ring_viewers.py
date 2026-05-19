"""Tests for `views/ring/ring_today.py` + `ring_next.py` + helper.

Cubre:
- helper `_format_offset`, `cita_and_suena`, `ring_dt`
- viewer behaviour: sin ring.json → mensaje;
  con ring.json → tabla; filtrado por día-de-alarma.
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


# ── viewers ─────────────────────────────────────────────────────────────


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


class TestRingTodayViewer:
    def test_no_ring_json_message(self, orbit_env):
        from views.ring import ring_today
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "Sin `ring.json`" in text

    def test_no_items_today_message(self, orbit_env):
        from views.ring import ring_today
        _write_ring_json(orbit_env["tmp"], [])
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "Sin alarmas programadas para hoy" in text

    def test_item_today_renders(self, orbit_env):
        from views.ring import ring_today
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
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "📅" in text
        assert "comida con Xabi" in text
        assert "13:00" in text
        assert "(-5m)" in text

    def test_item_tomorrow_with_one_day_alarm_appears_today(self, orbit_env):
        """alarm_minutes=1440 hace que un item de mañana suene HOY → debe aparecer."""
        from views.ring import ring_today
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
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "deadline" in text
        assert "(-1d)" in text
        assert tomorrow.strftime("%d/%m") in text  # cita muestra día explícito

    def test_item_tomorrow_with_5m_alarm_not_in_today(self, orbit_env):
        """alarm a 5m de un item de mañana NO aparece hoy."""
        from views.ring import ring_today
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
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "tarea mañana" not in text
        assert "Sin alarmas programadas para hoy" in text

    def test_disabled_ring_shows_in_header(self, orbit_env):
        from views.ring import ring_today
        _write_ring_json(orbit_env["tmp"], [], enabled=False)
        out = orbit_env["tmp"] / "ring-today.md"
        ring_today.generate(out)
        text = out.read_text()
        assert "ring deshabilitado" in text


class TestRingNextViewer:
    def test_no_ring_json_message(self, orbit_env):
        from views.ring import ring_next
        out = orbit_env["tmp"] / "ring-next.md"
        ring_next.generate(out)
        text = out.read_text()
        assert "Sin `ring.json`" in text

    def test_groups_by_ring_day(self, orbit_env):
        from views.ring import ring_next
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
        out = orbit_env["tmp"] / "ring-next.md"
        ring_next.generate(out)
        text = out.read_text()
        # dos sub-headers de día
        assert f"## {today.isoformat()}" in text
        assert f"## {d2.isoformat()}" in text
        # ambos items presentes
        assert "hoy" in text
        assert "pasado mañana" in text

    def test_ring_in_past_excluded(self, orbit_env):
        """Item cuyo ring ya pasó NO aparece en ring-next."""
        from views.ring import ring_next
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
        out = orbit_env["tmp"] / "ring-next.md"
        ring_next.generate(out)
        text = out.read_text()
        assert "antiguo" not in text
        assert "Sin alarmas programadas" in text
