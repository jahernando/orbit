"""core/dateparse.py — natural language date parser.

Accepts standard formats unchanged (YYYY-MM-DD, YYYY-MM, YYYY-Wnn).
Translates natural expressions (English and Spanish) into standard formats:
  - day expressions  → YYYY-MM-DD
  - week expressions → YYYY-Wnn
  - month expressions→ YYYY-MM
"""

import re
from datetime import date, timedelta
import calendar as _calendar
from typing import Optional

from core.config import normalize as _norm


# ── Vocabulary ────────────────────────────────────────────────────────────────

WEEKDAYS_EN   = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS_ES   = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

MONTHS_EN = ["january", "february", "march", "april", "may", "june",
             "july", "august", "september", "october", "november", "december"]
MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _week_key(d: date) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _parse_weekday(token: str) -> Optional[int]:
    n = _norm(token)
    if n in WEEKDAYS_EN:
        return WEEKDAYS_EN.index(n)
    if n in WEEKDAYS_ES:
        return WEEKDAYS_ES.index(n)
    return None


def _parse_month_num(token: str) -> Optional[int]:
    n = _norm(token)
    if n in MONTHS_EN:
        return MONTHS_EN.index(n) + 1
    if n in MONTHS_ES:
        return MONTHS_ES.index(n) + 1
    return None


def _next_weekday(today: date, wd: int) -> date:
    days = (wd - today.weekday()) % 7 or 7
    return today + timedelta(days=days)


def _last_weekday_occurrence(today: date, wd: int) -> date:
    days = (today.weekday() - wd) % 7 or 7
    return today - timedelta(days=days)


def _last_weekday_of_month(year: int, month: int, wd: int) -> date:
    last = _calendar.monthrange(year, month)[1]
    d = date(year, month, last)
    while d.weekday() != wd:
        d -= timedelta(days=1)
    return d


def _first_weekday_of_month(year: int, month: int, wd: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


def _add_months(d: date, n: int) -> date:
    month = d.month + n
    year  = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day   = min(d.day, _calendar.monthrange(year, month)[1])
    return date(year, month, day)


# ── Public API ────────────────────────────────────────────────────────────────

def parse_date(expr: str) -> str:
    """Parse a date expression and return a standard date string.

    Standard formats are returned unchanged.
    Unrecognised expressions are returned as-is (callers will raise a clear error).
    """
    expr = expr.strip()

    # Already standard — pass through
    if re.match(r'^\d{4}-\d{2}-\d{2}$', expr):
        return expr
    if re.match(r'^\d{4}-\d{2}$', expr):
        return expr
    if re.match(r'^\d{4}-W\d{2}$', expr):
        return expr

    # Near-standard: YYYY-M-D or YYYY-MM-D or YYYY-M-DD — zero-pad
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', expr)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # Near-standard: YYYY-M — zero-pad month
    m = re.match(r'^(\d{4})-(\d)$', expr)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"

    today = date.today()
    n = _norm(expr)

    # ── Simple day ────────────────────────────────────────────────────────
    if n in ("today", "hoy"):
        return today.isoformat()
    if n in ("yesterday", "ayer"):
        return (today - timedelta(days=1)).isoformat()
    if n in ("tomorrow", "manana", "mañana"):
        return (today + timedelta(days=1)).isoformat()

    # ── Week ──────────────────────────────────────────────────────────────
    if n in ("this week", "esta semana"):
        return _week_key(today)
    if n in ("last week", "semana pasada", "la semana pasada"):
        return _week_key(today - timedelta(weeks=1))
    if n in ("next week", "proxima semana", "la proxima semana", "semana que viene"):
        return _week_key(today + timedelta(weeks=1))

    # ── Month ─────────────────────────────────────────────────────────────
    if n in ("this month", "este mes"):
        return today.strftime("%Y-%m")
    if n in ("last month", "mes pasado", "el mes pasado"):
        return _add_months(today, -1).strftime("%Y-%m")
    if n in ("next month", "proximo mes", "el proximo mes"):
        return _add_months(today, 1).strftime("%Y-%m")

    # ── "in N days / weeks / months" ─────────────────────────────────────
    m = re.match(r'^in (\d+) (days?|weeks?|months?)$', n)
    if not m:
        m = re.match(r'^en (\d+) (d[ií]as?|semanas?|meses?)$', n)
    if m:
        val  = int(m.group(1))
        unit = _norm(m.group(2))
        if unit.startswith("d"):              # day/days/día/días
            return (today + timedelta(days=val)).isoformat()
        if unit.startswith(("w", "s")):    # week/weeks/semana/semanas
            return (today + timedelta(weeks=val)).isoformat()
        if unit.startswith("m"):           # month/months/mes/meses
            return _add_months(today, val).isoformat()

    # ── "last/último weekday of/de month" ────────────────────────────────
    m = re.match(r'^(?:last|ultimo) (.+?) (?:of|de) (.+)$', n)
    if m:
        wd = _parse_weekday(m.group(1))
        mn = _parse_month_num(m.group(2))
        if wd is not None and mn is not None:
            year = today.year if mn >= today.month else today.year + 1
            return _last_weekday_of_month(year, mn, wd).isoformat()

    # ── "first/primer weekday of/de month" ───────────────────────────────
    m = re.match(r'^(?:first|primer(?:o)?) (.+?) (?:of|de) (.+)$', n)
    if m:
        wd = _parse_weekday(m.group(1))
        mn = _parse_month_num(m.group(2))
        if wd is not None and mn is not None:
            year = today.year if mn >= today.month else today.year + 1
            return _first_weekday_of_month(year, mn, wd).isoformat()

    # ── "next weekday" ────────────────────────────────────────────────────
    m = re.match(r'^(?:next|proximo|el proximo) (.+)$', n)
    if m:
        wd = _parse_weekday(m.group(1))
        if wd is not None:
            return _next_weekday(today, wd).isoformat()

    # ── "last weekday" / "weekday pasado" / "el weekday pasado" ──────────
    m = re.match(r'^(?:last|el ultimo) (.+)$', n)
    if m:
        wd = _parse_weekday(m.group(1))
        if wd is not None:
            return _last_weekday_occurrence(today, wd).isoformat()

    m = re.match(r'^(?:el )?(.+?) pasado$', n)
    if m:
        wd = _parse_weekday(m.group(1))
        if wd is not None:
            return _last_weekday_occurrence(today, wd).isoformat()

    # ── bare weekday name → next occurrence ──────────────────────────────
    wd = _parse_weekday(n)
    if wd is not None:
        return _next_weekday(today, wd).isoformat()

    # Unrecognised — return as-is
    return expr
