"""test_dateparse.py — unit tests for natural language date parsing.

Covers:
  - Standard formats pass-through (YYYY-MM-DD, YYYY-MM, YYYY-Wnn)
  - Simple day expressions: today/hoy, yesterday/ayer, tomorrow/mañana
  - Week expressions: this/last/next week (en/es)
  - Month expressions: this/last/next month (en/es)
  - Relative: in N days/weeks/months, en N días/semanas/meses
  - last/first weekday of month (en/es)
  - next/próximo weekday, last/pasado weekday
  - Edge cases: accents, unrecognised input, whitespace
  - Helper functions: _add_months, _next_weekday, _last_weekday_occurrence
"""

import pytest
from datetime import date, timedelta
from unittest.mock import patch

from core.dateparse import (
    parse_date, _norm, _parse_weekday, _parse_month_num,
    _next_weekday, _last_weekday_occurrence,
    _last_weekday_of_month, _first_weekday_of_month,
    _add_months, _week_key,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestNorm:

    def test_lowercase(self):
        assert _norm("TODAY") == "today"

    def test_strips_accents(self):
        assert _norm("mañana") == "manana"
        assert _norm("próximo") == "proximo"
        assert _norm("miércoles") == "miercoles"

    def test_strips_whitespace(self):
        assert _norm("  hoy  ") == "hoy"


class TestParseWeekday:

    def test_english_weekdays(self):
        assert _parse_weekday("monday") == 0
        assert _parse_weekday("friday") == 4
        assert _parse_weekday("sunday") == 6

    def test_spanish_weekdays(self):
        assert _parse_weekday("lunes") == 0
        assert _parse_weekday("viernes") == 4
        assert _parse_weekday("domingo") == 6

    def test_accented_weekday(self):
        # miércoles → miercoles after _norm
        assert _parse_weekday("miércoles") == 2
        assert _parse_weekday("sábado") == 5

    def test_unknown_returns_none(self):
        assert _parse_weekday("notaday") is None


class TestParseMonthNum:

    def test_english_months(self):
        assert _parse_month_num("january") == 1
        assert _parse_month_num("december") == 12

    def test_spanish_months(self):
        assert _parse_month_num("enero") == 1
        assert _parse_month_num("diciembre") == 12

    def test_unknown_returns_none(self):
        assert _parse_month_num("notamonth") is None


class TestWeekKey:

    def test_week_key_format(self):
        d = date(2026, 1, 5)  # Monday of week 2
        assert _week_key(d) == "2026-W02"

    def test_week_key_year_boundary(self):
        d = date(2025, 12, 29)  # Could be week 1 of 2026
        key = _week_key(d)
        assert key.startswith("2026-W01") or key.startswith("2025-W")


class TestNextWeekday:

    def test_next_monday_from_monday(self):
        # If today is Monday, next Monday is 7 days away
        monday = date(2026, 3, 9)  # Monday
        assert monday.weekday() == 0
        result = _next_weekday(monday, 0)
        assert result == date(2026, 3, 16)

    def test_next_friday_from_monday(self):
        monday = date(2026, 3, 9)
        result = _next_weekday(monday, 4)  # Friday
        assert result == date(2026, 3, 13)

    def test_next_wednesday_from_thursday(self):
        thursday = date(2026, 3, 12)
        result = _next_weekday(thursday, 2)  # Wednesday
        assert result == date(2026, 3, 18)


class TestLastWeekdayOccurrence:

    def test_last_friday_from_monday(self):
        monday = date(2026, 3, 9)
        result = _last_weekday_occurrence(monday, 4)  # Friday
        assert result == date(2026, 3, 6)

    def test_last_monday_from_monday(self):
        # Same weekday = 7 days ago
        monday = date(2026, 3, 9)
        result = _last_weekday_occurrence(monday, 0)
        assert result == date(2026, 3, 2)


class TestLastWeekdayOfMonth:

    def test_last_friday_of_march_2026(self):
        result = _last_weekday_of_month(2026, 3, 4)  # Friday
        assert result == date(2026, 3, 27)

    def test_last_sunday_of_february_2026(self):
        result = _last_weekday_of_month(2026, 2, 6)  # Sunday
        assert result == date(2026, 2, 22)


class TestFirstWeekdayOfMonth:

    def test_first_monday_of_march_2026(self):
        result = _first_weekday_of_month(2026, 3, 0)  # Monday
        assert result == date(2026, 3, 2)

    def test_first_sunday_of_march_2026(self):
        result = _first_weekday_of_month(2026, 3, 6)  # Sunday
        assert result == date(2026, 3, 1)


class TestAddMonths:

    def test_add_one_month(self):
        assert _add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)

    def test_add_across_year(self):
        assert _add_months(date(2026, 11, 10), 3) == date(2027, 2, 10)

    def test_subtract_month(self):
        assert _add_months(date(2026, 3, 15), -1) == date(2026, 2, 15)

    def test_clamp_day_to_month_end(self):
        # Jan 31 + 1 month → Feb 28
        assert _add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)

    def test_leap_year(self):
        assert _add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_subtract_across_year(self):
        assert _add_months(date(2026, 1, 15), -2) == date(2025, 11, 15)


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — standard formats
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateStandard:

    def test_iso_date(self):
        assert parse_date("2026-03-10") == "2026-03-10"

    def test_iso_month(self):
        assert parse_date("2026-03") == "2026-03"

    def test_iso_week(self):
        assert parse_date("2026-W10") == "2026-W10"

    def test_whitespace_stripped(self):
        assert parse_date("  2026-03-10  ") == "2026-03-10"

    def test_unrecognised_returned_as_is(self):
        assert parse_date("gibberish") == "gibberish"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — simple days (patched today = 2026-03-10, Tuesday)
# ═══════════════════════════════════════════════════════════════════════════════

_TODAY = date(2026, 3, 10)


def _patch_today(fn):
    """Decorator to patch date.today() to 2026-03-10 (Tuesday)."""
    def wrapper(*args, **kwargs):
        with patch("core.dateparse.date") as mock_date:
            mock_date.today.return_value = _TODAY
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            mock_date.fromisoformat = date.fromisoformat
            return fn(*args, **kwargs)
    return wrapper


class TestParseDateSimpleDays:

    @_patch_today
    def test_today_en(self):
        assert parse_date("today") == "2026-03-10"

    @_patch_today
    def test_hoy(self):
        assert parse_date("hoy") == "2026-03-10"

    @_patch_today
    def test_yesterday_en(self):
        assert parse_date("yesterday") == "2026-03-09"

    @_patch_today
    def test_ayer(self):
        assert parse_date("ayer") == "2026-03-09"

    @_patch_today
    def test_tomorrow_en(self):
        assert parse_date("tomorrow") == "2026-03-11"

    @_patch_today
    def test_manana_with_accent(self):
        assert parse_date("mañana") == "2026-03-11"

    @_patch_today
    def test_manana_without_accent(self):
        assert parse_date("manana") == "2026-03-11"

    @_patch_today
    def test_case_insensitive(self):
        assert parse_date("TODAY") == "2026-03-10"
        assert parse_date("Hoy") == "2026-03-10"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — weeks
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateWeeks:

    @_patch_today
    def test_this_week(self):
        result = parse_date("this week")
        assert result == _week_key(_TODAY)

    @_patch_today
    def test_esta_semana(self):
        result = parse_date("esta semana")
        assert result == _week_key(_TODAY)

    @_patch_today
    def test_last_week(self):
        result = parse_date("last week")
        assert result == _week_key(_TODAY - timedelta(weeks=1))

    @_patch_today
    def test_semana_pasada(self):
        result = parse_date("semana pasada")
        assert result == _week_key(_TODAY - timedelta(weeks=1))

    @_patch_today
    def test_next_week(self):
        result = parse_date("next week")
        assert result == _week_key(_TODAY + timedelta(weeks=1))

    @_patch_today
    def test_proxima_semana(self):
        result = parse_date("próxima semana")
        assert result == _week_key(_TODAY + timedelta(weeks=1))

    @_patch_today
    def test_semana_que_viene(self):
        result = parse_date("semana que viene")
        assert result == _week_key(_TODAY + timedelta(weeks=1))


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — months
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateMonths:

    @_patch_today
    def test_this_month(self):
        assert parse_date("this month") == "2026-03"

    @_patch_today
    def test_este_mes(self):
        assert parse_date("este mes") == "2026-03"

    @_patch_today
    def test_last_month(self):
        assert parse_date("last month") == "2026-02"

    @_patch_today
    def test_mes_pasado(self):
        assert parse_date("mes pasado") == "2026-02"

    @_patch_today
    def test_next_month(self):
        assert parse_date("next month") == "2026-04"

    @_patch_today
    def test_proximo_mes(self):
        assert parse_date("próximo mes") == "2026-04"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — relative (in N units)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateRelative:

    @_patch_today
    def test_in_5_days(self):
        assert parse_date("in 5 days") == "2026-03-15"

    @_patch_today
    def test_en_5_dias(self):
        assert parse_date("en 5 días") == "2026-03-15"

    @_patch_today
    def test_in_1_day(self):
        assert parse_date("in 1 day") == "2026-03-11"

    @_patch_today
    def test_in_2_weeks(self):
        assert parse_date("in 2 weeks") == "2026-03-24"

    @_patch_today
    def test_en_2_semanas(self):
        assert parse_date("en 2 semanas") == "2026-03-24"

    @_patch_today
    def test_in_3_months(self):
        assert parse_date("in 3 months") == "2026-06-10"

    @_patch_today
    def test_en_1_mes(self):
        assert parse_date("en 1 meses") == "2026-04-10"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — last/first weekday of month
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateWeekdayOfMonth:

    @_patch_today
    def test_last_friday_of_march(self):
        assert parse_date("last friday of march") == "2026-03-27"

    @_patch_today
    def test_ultimo_viernes_de_marzo(self):
        assert parse_date("último viernes de marzo") == "2026-03-27"

    @_patch_today
    def test_first_monday_of_april(self):
        assert parse_date("first monday of april") == "2026-04-06"

    @_patch_today
    def test_primer_lunes_de_abril(self):
        assert parse_date("primer lunes de abril") == "2026-04-06"

    @_patch_today
    def test_primero_lunes_de_abril(self):
        assert parse_date("primero lunes de abril") == "2026-04-06"

    @_patch_today
    def test_future_month_same_year(self):
        # March is current month, so "last X of march" should be this year
        result = parse_date("last monday of march")
        assert result == "2026-03-30"

    @_patch_today
    def test_past_month_next_year(self):
        # January is past, so "last X of january" should be next year
        result = parse_date("last monday of january")
        assert result == "2027-01-25"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_date — next/last weekday
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateNextLastWeekday:

    @_patch_today
    def test_next_friday(self):
        # Today is Tuesday 2026-03-10, next Friday = 2026-03-13
        assert parse_date("next friday") == "2026-03-13"

    @_patch_today
    def test_proximo_viernes(self):
        assert parse_date("próximo viernes") == "2026-03-13"

    @_patch_today
    def test_next_tuesday(self):
        # Today is Tuesday, next Tuesday = 7 days later
        assert parse_date("next tuesday") == "2026-03-17"

    @_patch_today
    def test_last_monday(self):
        # Today is Tuesday, last Monday = 2026-03-09
        assert parse_date("last monday") == "2026-03-09"

    @_patch_today
    def test_lunes_pasado(self):
        assert parse_date("lunes pasado") == "2026-03-09"

    @_patch_today
    def test_el_lunes_pasado(self):
        assert parse_date("el lunes pasado") == "2026-03-09"

    @_patch_today
    def test_last_tuesday(self):
        # Today is Tuesday, last Tuesday = 7 days ago
        assert parse_date("last tuesday") == "2026-03-03"


# ═══════════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseDateZeroPad:
    """Dates with single-digit month/day are zero-padded automatically."""

    def test_single_digit_day(self):
        assert parse_date("2026-03-9") == "2026-03-09"

    def test_single_digit_month(self):
        assert parse_date("2026-3-09") == "2026-03-09"

    def test_both_single_digit(self):
        assert parse_date("2026-3-9") == "2026-03-09"

    def test_single_digit_month_only(self):
        assert parse_date("2026-3") == "2026-03"

    def test_already_padded_unchanged(self):
        assert parse_date("2026-03-10") == "2026-03-10"
        assert parse_date("2026-03") == "2026-03"


class TestDateDispatcher:
    """Test the _d() function in orbit.py that wraps parse_date."""

    def test_none_returns_none(self):
        from orbit import _d
        assert _d(None) is None
        assert _d("") is None

    def test_none_keyword_passes_through(self):
        from orbit import _d
        assert _d("none") == "none"
        assert _d("None") == "none"

    def test_valid_dates(self):
        from orbit import _d
        assert _d("2026-03-10") == "2026-03-10"
        assert _d("2026-3-9") == "2026-03-09"
        assert _d("2026-03") == "2026-03"

    def test_invalid_date_raises(self):
        import pytest
        from orbit import _d
        with pytest.raises(SystemExit):
            _d("asdf")

    def test_invalid_partial_raises(self):
        import pytest
        from orbit import _d
        with pytest.raises(SystemExit):
            _d("2026")


class TestParseDateEdgeCases:

    def test_empty_string(self):
        assert parse_date("") == ""

    def test_unrecognised_passthrough(self):
        assert parse_date("not a date") == "not a date"

    def test_partial_iso_passthrough(self):
        assert parse_date("2026") == "2026"

    @_patch_today
    def test_mixed_case(self):
        assert parse_date("NEXT FRIDAY") == "2026-03-13"
        assert parse_date("Last Month") == "2026-02"
