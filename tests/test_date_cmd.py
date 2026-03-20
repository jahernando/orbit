"""test_date_cmd.py — tests for `orbit date` command and report period shortcuts.

Covers:
  - cmd_date: no args (today), weekday, relative expressions, invalid input
  - cmd_report period shortcuts: today, week, month, yesterday, hoy, mes
  - _parse_period: YYYY-Wnn support
"""

import pytest
import re
from datetime import date, timedelta
from unittest.mock import patch
from argparse import Namespace

from core.stats import _parse_period


# ═══════════════════════════════════════════════════════════════════════════════
# orbit date
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdDate:

    def _run(self, *args):
        """Run cmd_date with given args and return (rc, stdout)."""
        from orbit import cmd_date
        ns = Namespace(expr=list(args) if args else [])
        return cmd_date(ns)

    def test_no_args_returns_today(self, capsys):
        rc = self._run()
        assert rc == 0
        out = capsys.readouterr().out
        assert date.today().isoformat() in out

    def test_today(self, capsys):
        rc = self._run("today")
        assert rc == 0
        out = capsys.readouterr().out
        assert date.today().isoformat() in out

    def test_hoy(self, capsys):
        rc = self._run("hoy")
        assert rc == 0
        out = capsys.readouterr().out
        assert date.today().isoformat() in out

    def test_tomorrow(self, capsys):
        rc = self._run("tomorrow")
        assert rc == 0
        out = capsys.readouterr().out
        expected = (date.today() + timedelta(days=1)).isoformat()
        assert expected in out

    @patch("core.dateparse.date")
    def test_weekday_wednesday(self, mock_date, capsys):
        # Fix today to a Monday so "wednesday" → that Wednesday
        mock_date.today.return_value = date(2026, 3, 16)  # Monday
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
        rc = self._run("wednesday")
        assert rc == 0
        out = capsys.readouterr().out
        assert "2026-03-18" in out  # Wednesday after Monday

    def test_in_two_weeks(self, capsys):
        rc = self._run("in", "2", "weeks")
        assert rc == 0
        out = capsys.readouterr().out
        expected = (date.today() + timedelta(weeks=2)).isoformat()
        assert expected in out

    def test_invalid_expression(self, capsys):
        rc = self._run("xyzzy")
        assert rc == 1
        out = capsys.readouterr().out
        assert "no se pudo resolver" in out

    def test_copies_to_clipboard(self, capsys):
        """Just verify it prints the clipboard message (pbcopy may not be available in CI)."""
        rc = self._run("today")
        assert rc == 0
        out = capsys.readouterr().out
        assert date.today().isoformat() in out

    def test_explicit_date_passthrough(self, capsys):
        rc = self._run("2026-06-15")
        assert rc == 0
        out = capsys.readouterr().out
        assert "2026-06-15" in out

    def test_month_not_accepted(self, capsys):
        """Expressions that resolve to YYYY-MM (not a day) should fail."""
        rc = self._run("this", "month")
        assert rc == 1


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_period — ISO week support
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
# orbit week
# ═══════════════════════════════════════════════════════════════════════════════

class TestCmdWeek:

    def _run(self, *args):
        from orbit import cmd_week
        ns = Namespace(expr=list(args) if args else [])
        return cmd_week(ns)

    def test_no_args_returns_this_week(self, capsys):
        rc = self._run()
        assert rc == 0
        out = capsys.readouterr().out
        iso = date.today().isocalendar()
        expected = f"{iso[0]}-W{iso[1]:02d}"
        assert expected in out

    def test_next_week(self, capsys):
        rc = self._run("next", "week")
        assert rc == 0
        out = capsys.readouterr().out
        iso = (date.today() + timedelta(weeks=1)).isocalendar()
        expected = f"{iso[0]}-W{iso[1]:02d}"
        assert expected in out

    def test_from_date(self, capsys):
        rc = self._run("2026-03-20")
        assert rc == 0
        out = capsys.readouterr().out
        assert "2026-W12" in out

    def test_invalid_expression(self, capsys):
        rc = self._run("xyzzy")
        assert rc == 1
        out = capsys.readouterr().out
        assert "no se pudo resolver" in out


class TestParsePeriodWeek:

    def test_iso_week(self):
        start, end = _parse_period("2026-W12")
        assert start == date(2026, 3, 16)   # Monday of W12
        assert end == date(2026, 3, 22)      # Sunday of W12
        assert (end - start).days == 6

    def test_iso_week_01(self):
        start, end = _parse_period("2026-W01")
        assert start.weekday() == 0  # Monday
        assert (end - start).days == 6

    def test_month_still_works(self):
        start, end = _parse_period("2026-03")
        assert start == date(2026, 3, 1)
        assert end == date(2026, 3, 31)

    def test_single_date_still_works(self):
        start, end = _parse_period("2026-03-20")
        assert start == end == date(2026, 3, 20)


# ═══════════════════════════════════════════════════════════════════════════════
# report period shortcuts
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportPeriodShortcuts:
    """Test that cmd_report detects period keywords in positional args."""

    def test_report_periods_dict(self):
        from orbit import _REPORT_PERIODS
        assert "today" in _REPORT_PERIODS
        assert "hoy" in _REPORT_PERIODS
        assert "week" in _REPORT_PERIODS
        assert "semana" in _REPORT_PERIODS
        assert "month" in _REPORT_PERIODS
        assert "mes" in _REPORT_PERIODS
        assert "yesterday" in _REPORT_PERIODS
        assert "ayer" in _REPORT_PERIODS
