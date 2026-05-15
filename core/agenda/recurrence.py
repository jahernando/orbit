"""recurrence — grammar and arithmetic for orbit recurrence expressions.

Orbit stores recurrence as a small DSL on the agenda line (after ``🔄``):

    daily | weekly | monthly | weekdays
    every-N-{days,weeks,months}
    {first,last}-{monday,..,sunday|lunes,..,domingo}

This module exposes:
  * :data:`VALID_RECUR` — the canonical set of basic keys.
  * :func:`_normalize_recur` / :func:`is_valid_recur` — grammar layer.
  * :func:`_next_occurrence` — "next date after this one" arithmetic,
    delegated to :mod:`dateutil` (ADR-030).
  * :func:`_advance_to_today_or_future` — multi-step advance used at
    shell startup when a recurring item is several periods overdue.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrule, DAILY, MONTHLY, MO, TU, WE, TH, FR, SA, SU


VALID_RECUR = {"daily", "weekly", "monthly", "weekdays"}

# Maps weekday names (English + Spanish) to dateutil.rrule weekday tokens.
_WEEKDAY_RRULE = {
    "monday": MO,    "tuesday": TU,   "wednesday": WE, "thursday": TH,
    "friday": FR,    "saturday": SA,  "sunday": SU,
    "lunes":  MO,    "martes":  TU,   "miercoles": WE, "jueves":   TH,
    "viernes": FR,   "sabado":  SA,   "domingo":   SU,
}

_EVERY_RE = re.compile(r"^every[- ](\d+)[- ](days?|weeks?|months?)$")
_POS_RE   = re.compile(r"^(first|last|1st)[- ](monday|tuesday|wednesday|thursday|friday|saturday|sunday"
                        r"|lunes|martes|miercoles|jueves|viernes|sabado|domingo)$")


def _normalize_recur(raw: str) -> str:
    """Normalize a recurrence expression to its stored key.

    Accepts:
      daily, weekly, monthly, weekdays           → as-is
      "every 2 weeks" / "every-2-weeks"          → every-2-weeks
      "every 3 days"                             → every-3-days
      "first monday" / "first-monday"            → first-monday
      "last friday"  / "last-friday"             → last-friday
    Returns the canonical key or the original string if not recognized.
    """
    s = raw.strip().lower().replace(" ", "-")
    if s in VALID_RECUR:
        return s
    if _EVERY_RE.match(s):
        m = _EVERY_RE.match(s)
        n = int(m.group(1))
        unit = m.group(2).rstrip("s")  # day/week/month
        return f"every-{n}-{unit}s"
    if _POS_RE.match(s):
        m = _POS_RE.match(s)
        pos = "first" if m.group(1) in ("first", "1st") else "last"
        return f"{pos}-{m.group(2)}"
    return raw


def is_valid_recur(raw: str) -> bool:
    """Check if a recurrence expression is valid."""
    key = _normalize_recur(raw)
    if key in VALID_RECUR:
        return True
    if _EVERY_RE.match(key):
        return True
    if _POS_RE.match(key):
        return True
    return False


def _next_occurrence(due: Optional[str], recur: str, done_date: str) -> str:
    """Compute next recurrence date after completing a task.

    Delegates the calendar arithmetic to :mod:`dateutil`:
      * ``relativedelta(months=N)`` for ``monthly`` / ``every-N-months`` —
        gives the natural "clamp to last day if the target month is short"
        behaviour (31-Jan + 1 month → 28-Feb).
      * ``rrule(DAILY, byweekday=MO..FR)`` for ``weekdays``.
      * ``rrule(MONTHLY, byweekday=X, bysetpos=±1)`` for ``first-X`` /
        ``last-X`` — encodes "first/last X of next month" directly.
    The trivial ``daily`` / ``weekly`` / ``every-N-{days,weeks}`` paths
    stay on plain :func:`timedelta`.
    """
    base = date.fromisoformat(due) if due else date.fromisoformat(done_date)
    if recur == "daily":
        nxt = base + timedelta(days=1)
    elif recur == "weekly":
        nxt = base + timedelta(weeks=1)
    elif recur == "monthly":
        nxt = base + relativedelta(months=1)
    elif recur == "weekdays":
        nxt = next(iter(rrule(DAILY, dtstart=base + timedelta(days=1),
                              byweekday=(MO, TU, WE, TH, FR), count=1))).date()
    elif (em := _EVERY_RE.match(recur)):
        n = int(em.group(1))
        unit = em.group(2).rstrip("s")
        if unit == "day":
            nxt = base + timedelta(days=n)
        elif unit == "week":
            nxt = base + timedelta(weeks=n)
        elif unit == "month":
            nxt = base + relativedelta(months=n)
        else:
            nxt = base + timedelta(weeks=1)
    elif (pm := _POS_RE.match(recur)):
        wd = _WEEKDAY_RRULE.get(pm.group(2), MO)
        pos = +1 if pm.group(1) in ("first", "1st") else -1
        anchor = base + relativedelta(months=1, day=1)
        nxt = next(iter(rrule(MONTHLY, dtstart=anchor, byweekday=wd,
                              bysetpos=pos, count=1))).date()
    else:
        nxt = base + timedelta(weeks=1)
    return nxt.isoformat()


def _advance_to_today_or_future(item_date: str, recur: str,
                                 until: Optional[str]) -> tuple:
    """Advance a recurrence date forward until it reaches today or beyond.

    Returns (next_date_str, ended) where ended=True if series exceeded until.
    Handles cases where the user was away for multiple recurrence periods.
    """
    today = date.today()
    current = item_date
    while True:
        nxt = _next_occurrence(current, recur, today.isoformat())
        if until and date.fromisoformat(nxt) > date.fromisoformat(until):
            return nxt, True
        if date.fromisoformat(nxt) >= today:
            return nxt, False
        current = nxt
