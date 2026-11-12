"""FR-16's date rule: "Relative dates such as "next Friday" are converted using the meeting date as
reference" (docs/decisions.md D-125).

The model copies a deadline exactly as it was said (apps/ai/summarisation.py, rule 9), and this
module turns the phrase into a date, from the meeting's own date, by fixed rules. It is application
code for the reason citation verification is (invariant 5): a date the model computed would be a
judgement nobody could test, and a wrong one would look exactly like a right one.

**What it resolves**, with ``m`` the meeting date and weeks starting on Monday:

- an absolute date: ``2026-11-14``; ``14/11/2026`` or ``14/11`` (day first, as written in
  Australia); ``14 November``, ``14th of November``, ``the fourteenth of November``,
  ``November 14``, with or without a year. Without a year it is the next such date on or after m;
- a day of the month alone, ``the 14th`` or ``the fourteenth``: the next 14th on or after m. With
  a weekday, ``Wednesday the 28th``, the weekday must agree with that date, or nothing is resolved;
- ``today``, ``tonight``, ``end of the day``: m. ``tomorrow``: m + 1. ``the day after
  tomorrow``: m + 2;
- ``in N days``, ``within N days``, ``in N weeks``, ``in a week``, ``in a fortnight``;
- a weekday, ``Friday`` or ``this Friday``: the first Friday after m;
- ``next Friday``: the Friday of the calendar week after m's. This is the proposal's own example,
  and the reading this module fixes: said on a Tuesday, it is the Friday ten days later, not three;
- ``end of the week``: the Friday of m's week (the next Friday, said at a weekend);
  ``end of next week``: the Friday a week after that; ``end of the month``: the month's last day;
  ``end of next month``: the next month's last day; ``end of January``: that month's last day.

Leading connectives (``by``, ``on``, ``before``, ``due``, ``until``, ``no later than``, ``for``)
and a time of day are ignored, whether it trails (``Friday afternoon``, ``Thursday night``,
``Friday close of business``, ``tomorrow at the latest``) or leads (``end of day tomorrow``,
``close of business Friday``): the day is what is resolved. **Anything else resolves to None, and
the phrase is kept**: ``next week``,
``this week``, ``soon``, ``the week after next``, ``over the weekend``, ``after the audit``,
``once finance approves``. A date is never invented: the person sees the phrase and can set one.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
FRIDAY = WEEKDAYS.index("friday")

MONTHS = {
    name: number
    for number, names in enumerate(
        (
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for name in names
}

_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "thirtieth": 30,
}
for _unit in ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth"):
    _ORDINAL_WORDS[f"twenty-{_unit}"] = _ORDINAL_WORDS[f"twenty {_unit}"] = 20 + _ORDINAL_WORDS[_unit]
_ORDINAL_WORDS["thirty-first"] = _ORDINAL_WORDS["thirty first"] = 31

_COUNT_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}

# Words in front of the deadline that do not change it, any number of them: "by", "due by", "no
# later than". "end of" is not among them: it does change the date.
_LEADING = re.compile(r"^(?:(?:no later than|not later than|by|on|before|due|until|till|for|at)\s+)+")
_TRAILING = re.compile(
    r"\s+(?:at the latest|latest|morning|afternoon|evening|night|"
    r"(?:by )?(?:the )?(?:end|close) of (?:the )?(?:day|business)|cob|eod)$"
)
# A time of day in front of the day it belongs to: "end of day tomorrow", "close of business
# Friday". Only where something follows it; on its own, "end of the day" is the meeting's day.
_LEADING_TIME_OF_DAY = re.compile(
    r"^(?:the )?(?:(?:end|close) of (?:the )?(?:day|business)|cob|eod|first thing)(?: on)? (?=\S)"
)

_WEEKDAY = "(" + "|".join(WEEKDAYS) + ")"
_MONTH = "(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
_DAY = (
    r"(?:(\d{1,2})(?:st|nd|rd|th)?|("
    + "|".join(sorted((re.escape(word) for word in _ORDINAL_WORDS), key=len, reverse=True))
    + "))"
)
_YEAR = r"(\d{4})"

_END_OF = re.compile(r"(?:the )?end of (?:the |this )?(next )?(day|week|month)")


def _clean(phrase: str) -> str:
    text = phrase.casefold().replace("’", "'").strip()
    text = re.sub(r"[.,;:!?]+$", "", text)
    text = re.sub(r"\s+", " ", text)
    text = _LEADING.sub("", text)
    text = _LEADING_TIME_OF_DAY.sub("", text)
    if _END_OF.fullmatch(text):
        return text  # "the end of the day" is the whole phrase, not a time of day after one
    return _TRAILING.sub("", text).strip()


def _day(number: str | None, word: str | None) -> int | None:
    if number is not None:
        return int(number)
    return _ORDINAL_WORDS.get(word or "")


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_month_day(month: int, day: int, meeting: date) -> date | None:
    """The next ``day`` of ``month`` on or after the meeting: this year's, or else next year's."""
    this_year = _safe(meeting.year, month, day)
    if this_year is not None and this_year >= meeting:
        return this_year
    return _safe(meeting.year + 1, month, day)


def _next_day_of_month(day: int, meeting: date) -> date | None:
    """The next date on or after the meeting whose day of the month is ``day``."""
    if not 1 <= day <= 31:
        return None
    year, month = meeting.year, meeting.month
    for _ in range(13):
        candidate = _safe(year, month, day)
        if candidate is not None and candidate >= meeting:
            return candidate
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _end_of(next_one: bool, unit: str, m: date) -> date:
    if unit == "day":
        return m + timedelta(days=1) if next_one else m
    if unit == "week":
        friday = _week_start(m) + timedelta(days=FRIDAY)
        if friday < m:  # said at the weekend: the coming week's Friday
            friday += timedelta(days=7)
        return friday + timedelta(days=7) if next_one else friday
    year, month = m.year, m.month
    if next_one:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return _last_day(year, month)


def resolve_due_date(phrase: str | None, meeting_date: date) -> date | None:
    """The date ``phrase`` names, from ``meeting_date``, or None where the rules above fix none.

    **It never raises.** The phrase is a model's copy of uploaded text, and the caller is the
    transaction that stores a whole summary, so a phrase no date can hold ("in 99999999999
    weeks", a year past 9999) names no date, like any other phrase the rules do not fix. Without
    this, one such line in a transcript would cost the meeting its summary on every attempt.
    """
    if not phrase:
        return None
    try:
        return _resolve(phrase, meeting_date)
    except (OverflowError, ValueError):
        return None


def _resolve(phrase: str, meeting_date: date) -> date | None:
    text = _clean(phrase)
    m = meeting_date

    if text in ("today", "tonight", "close of business", "cob", "eod"):
        return m
    if text == "tomorrow":
        return m + timedelta(days=1)
    if text in ("the day after tomorrow", "day after tomorrow"):
        return m + timedelta(days=2)

    found = _END_OF.fullmatch(text)
    if found:
        return _end_of(bool(found.group(1)), found.group(2), m)
    # "end of January [2027]": that month's last day, the next one on or after the meeting.
    found = re.fullmatch(rf"(?:the )?end of {_MONTH}(?:,? {_YEAR})?", text)
    if found:
        month = MONTHS[found.group(1)]
        if found.group(2):
            return _last_day(int(found.group(2)), month)
        this_year = _last_day(m.year, month)
        return this_year if this_year >= m else _last_day(m.year + 1, month)

    found = re.fullmatch(r"(?:in|within) (\d+|[a-z]+) (days?|weeks?|fortnights?)", text)
    if found:
        count = int(found.group(1)) if found.group(1).isdigit() else _COUNT_WORDS.get(found.group(1))
        if count is None:
            return None
        unit = found.group(2)
        per = 14 if unit.startswith("fortnight") else 7 if unit.startswith("week") else 1
        return m + timedelta(days=count * per)
    if text in ("in a fortnight", "within a fortnight"):
        return m + timedelta(days=14)

    found = re.fullmatch(rf"(?:this )?{_WEEKDAY}", text)
    if found:
        offset = (WEEKDAYS.index(found.group(1)) - m.weekday()) % 7 or 7
        return m + timedelta(days=offset)
    found = re.fullmatch(rf"next {_WEEKDAY}", text)
    if found:
        return _week_start(m) + timedelta(days=7 + WEEKDAYS.index(found.group(1)))

    found = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if found:
        return _safe(int(found.group(1)), int(found.group(2)), int(found.group(3)))
    found = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?", text)
    if found:
        day, month = int(found.group(1)), int(found.group(2))
        if not 1 <= month <= 12:
            return None
        if found.group(3) is None:
            return _next_month_day(month, day, m)
        year = int(found.group(3))
        return _safe(year + 2000 if year < 100 else year, month, day)

    # "14 November [2026]", "14th of November", "the fourteenth of November".
    found = re.fullmatch(rf"(?:the )?{_DAY}(?: of)? {_MONTH}(?:,? {_YEAR})?", text)
    if found:
        day, month = _day(found.group(1), found.group(2)), MONTHS[found.group(3)]
        if day is None:
            return None
        return _safe(int(found.group(4)), month, day) if found.group(4) else _next_month_day(month, day, m)
    # "November 14[th][, 2026]", "November the 14th".
    found = re.fullmatch(rf"{_MONTH} (?:the )?{_DAY}(?:,? {_YEAR})?", text)
    if found:
        month, day = MONTHS[found.group(1)], _day(found.group(2), found.group(3))
        if day is None:
            return None
        return _safe(int(found.group(4)), month, day) if found.group(4) else _next_month_day(month, day, m)
    # "the 14th", "the fourteenth", optionally after a weekday that must agree.
    found = re.fullmatch(rf"(?:{_WEEKDAY},? )?the {_DAY}", text)
    if found:
        day = _day(found.group(2), found.group(3))
        resolved = _next_day_of_month(day, m) if day is not None else None
        if resolved is not None and found.group(1) and resolved.weekday() != WEEKDAYS.index(found.group(1)):
            return None  # "Wednesday the 28th" when the next 28th is not a Wednesday: ambiguous
        return resolved
    return None
