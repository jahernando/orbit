"""test_tasks.py — tests for task parsing.

Covers:
  - parse_task: basic, with time, with @ring, with @recur, [~], [x]
"""

from datetime import date, timedelta

import pytest

from core.tasks import parse_task


# ═══════════════════════════════════════════════════════════════════════════════
# parse_task — unit tests (no filesystem)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseTask:

    def test_basic_pending(self):
        t = parse_task("- [ ] Revisar paper (2026-03-15)")
        assert t["description"] == "Revisar paper"
        assert t["due"] == "2026-03-15"
        assert t["time"] is None
        assert t["done"] is False
        assert t["ring"] is False
        assert t["recur"] is None

    def test_pending_with_time(self):
        t = parse_task("- [ ] Reunión (2026-03-15 09:00)")
        assert t["due"] == "2026-03-15"
        assert t["time"] == "09:00"
        assert t["ring"] is False

    def test_ring_no_recur(self):
        t = parse_task("- [ ] Llamada (2026-03-15 10:00) @ring")
        assert t["due"] == "2026-03-15"
        assert t["time"] == "10:00"
        assert t["ring"] is True
        assert t["recur"] is None

    def test_ring_with_recur(self):
        t = parse_task("- [ ] Stand-up (2026-03-15 09:00) @ring @semanal")
        assert t["ring"] is True
        assert t["recur"] == "@semanal"
        assert t["due"] == "2026-03-15"
        assert t["time"] == "09:00"

    def test_recur_without_ring(self):
        t = parse_task("- [ ] Revisión (2026-03-15) @mensual")
        assert t["ring"] is False
        assert t["recur"] == "@mensual"
        assert t["due"] == "2026-03-15"
        assert t["time"] is None

    def test_scheduled_ring(self):
        """[~] = ring already sent to Reminders.app."""
        t = parse_task("- [~] Alarma (2026-03-15 08:00) @ring")
        assert t is not None
        assert t["done"] is False
        assert t["ring"] is True
        assert t["due"] == "2026-03-15"
        assert t["time"] == "08:00"

    def test_completed(self):
        t = parse_task("- [x] Tarea terminada (2026-03-10)")
        assert t["done"] is True
        assert t["completed"] == "2026-03-10"
        assert t["description"] == "Tarea terminada"

    def test_non_task_line_returns_none(self):
        assert parse_task("## Algún heading") is None
        assert parse_task("Texto normal") is None
        assert parse_task("") is None

    def test_no_date(self):
        t = parse_task("- [ ] Tarea sin fecha")
        assert t["due"] is None
        assert t["time"] is None
        assert t["description"] == "Tarea sin fecha"
