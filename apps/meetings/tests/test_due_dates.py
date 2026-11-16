"""FR-16's date rule (apps/meetings/due_dates.py, D-125): "Relative dates such as "next Friday"
are converted using the meeting date as reference."

The model copies a deadline as it was said and ``resolve_due_date`` turns the phrase into a date
by fixed rules, so every rule can be written down as a row of a table. The tables below are read
from one known day, **Tuesday 10 November 2026**, whose week runs Monday 9 to Sunday 15.

Three properties matter more than any one row:

- **The proposal's own example has one reading.** "Next Friday" said on a Tuesday is the Friday of
  the FOLLOWING week, ten days on; "Friday" and "this Friday" are the coming one, three days on.
- **A date is never invented.** A phrase the rules do not fix ("next week", "soon", "once finance
  approves") resolves to None, and so does an impossible date. Nothing raises: the phrase comes
  from a model reading an uploaded transcript, and a phrase that crashed this function would cost
  the meeting its whole summary.
- **Nothing said without a year resolves to a day before the meeting.** Checked over every
  meeting date of more than a year, a leap day and two year ends included.
- **A time of day is ignored wherever it sits.** "By end of day tomorrow" is tomorrow, and "close
  of business Friday" is Friday; on its own, "end of the day" is still the meeting's own day.

No database, no provider: a pure function of a phrase and a date.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pytest

from apps.meetings.due_dates import MONTHS, WEEKDAYS, resolve_due_date
from apps.meetings.tests.summary_builders import MEETING_DATE

TUESDAY = MEETING_DATE
MONDAY, TUESDAY_INDEX, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)


def nov(day: int) -> date:
    return date(2026, 11, day)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def test_the_reference_day_is_the_tuesday_the_tables_assume():
    assert TUESDAY == date(2026, 11, 10)
    assert TUESDAY.weekday() == TUESDAY_INDEX
    assert week_start(TUESDAY) == nov(9)


def check(table: dict, meeting: date = TUESDAY):
    wrong = {
        phrase: (resolve_due_date(phrase, meeting), expected)
        for phrase, expected in table.items()
        if resolve_due_date(phrase, meeting) != expected
    }
    assert wrong == {}, "phrase: (resolved, expected)"


# --- The proposal's example -----------------------------------------------------------------


def test_next_friday_from_a_tuesday_is_the_friday_of_the_following_week():
    """FR-16's own example. Said on Tuesday 10 November, "next Friday" is Friday 20 November,
    ten days on, and not the 13th: the Friday of the calendar week after the meeting's."""
    resolved = resolve_due_date("next Friday", TUESDAY)

    assert resolved == nov(20)
    assert (resolved - TUESDAY).days == 10
    assert resolved.weekday() == FRIDAY
    assert week_start(resolved) == week_start(TUESDAY) + timedelta(days=7)


@pytest.mark.parametrize("phrase", ["Friday", "this Friday", "friday", "on Friday", "by this Friday"])
def test_friday_and_this_friday_from_a_tuesday_are_the_coming_friday(phrase):
    resolved = resolve_due_date(phrase, TUESDAY)

    assert resolved == nov(13)
    assert (resolved - TUESDAY).days == 3
    assert resolved != resolve_due_date("next Friday", TUESDAY)


# --- Today, tomorrow, and counted days and weeks -------------------------------------------------


def test_the_day_words_from_the_meeting_date():
    check({
        "today": nov(10),
        "tonight": nov(10),
        "end of the day": nov(10),
        "end of day": nov(10),
        "the end of the day": nov(10),
        "tomorrow": nov(11),
        "the day after tomorrow": nov(12),
        "day after tomorrow": nov(12),
    })


def test_counted_days_weeks_and_fortnights():
    check({
        "in 3 days": nov(13),
        "in three days": nov(13),
        "in 1 day": nov(11),
        "in one day": nov(11),
        "in a day": nov(11),
        "within 10 days": nov(20),
        "within ten days": nov(20),
        "in a week": nov(17),
        "in 1 week": nov(17),
        "within a week": nov(17),
        "in 2 weeks": nov(24),
        "in two weeks": nov(24),
        "in a fortnight": nov(24),
        "within a fortnight": nov(24),
        "in 3 weeks": date(2026, 12, 1),
        "in 60 days": date(2027, 1, 9),
    })


@pytest.mark.parametrize("phrase", ["in a few days", "in several weeks", "in some days", "within many weeks",
                                    "in a couple of days", "in days", "in weeks"])
def test_a_count_that_is_not_a_number_is_not_guessed(phrase):
    assert resolve_due_date(phrase, TUESDAY) is None


# --- A weekday ------------------------------------------------------------------------------------


def test_a_weekday_is_the_first_such_day_after_the_meeting():
    check({
        "Wednesday": nov(11),
        "Thursday": nov(12),
        "Friday": nov(13),
        "Saturday": nov(14),
        "Sunday": nov(15),
        "Monday": nov(16),
        "this Monday": nov(16),
        "this Thursday": nov(12),
    })


@pytest.mark.parametrize("phrase", ["Tuesday", "this Tuesday", "on Tuesday", "by Tuesday"])
def test_a_weekday_said_on_that_weekday_is_seven_days_on(phrase):
    """"By Tuesday", said in Tuesday's meeting, is not the meeting's own day."""
    assert resolve_due_date(phrase, TUESDAY) == nov(17)


def test_next_weekday_is_that_day_of_the_following_calendar_week():
    check({
        "next Monday": nov(16),
        "next Tuesday": nov(17),
        "next Wednesday": nov(18),
        "next Thursday": nov(19),
        "next Friday": nov(20),
        "next Saturday": nov(21),
        "next Sunday": nov(22),
    })


@pytest.mark.parametrize("meeting_weekday", range(7), ids=WEEKDAYS)
def test_the_weekday_rules_hold_from_every_day_of_the_week(meeting_weekday):
    """Seven meeting days by seven named days. A bare or "this" weekday is one to seven days on
    and falls on that weekday; "next" falls on that weekday of the calendar week after the
    meeting's, weeks starting on Monday."""
    meeting = nov(9) + timedelta(days=meeting_weekday)
    assert meeting.weekday() == meeting_weekday

    for index, name in enumerate(WEEKDAYS):
        for phrase in (name, f"this {name}"):
            coming = resolve_due_date(phrase, meeting)
            assert coming.weekday() == index, (phrase, meeting)
            assert 1 <= (coming - meeting).days <= 7, (phrase, meeting)
            assert ((coming - meeting).days == 7) == (index == meeting_weekday), (phrase, meeting)

        following = resolve_due_date(f"next {name}", meeting)
        assert following.weekday() == index, (name, meeting)
        assert week_start(following) == week_start(meeting) + timedelta(days=7), (name, meeting)
        assert following > meeting


# --- The end of a week or a month --------------------------------------------------------------------


def test_the_end_of_the_week_and_month_from_a_tuesday():
    check({
        "end of the week": nov(13),
        "end of this week": nov(13),
        "the end of the week": nov(13),
        "end of week": nov(13),
        "end of next week": nov(20),
        "the end of next week": nov(20),
        "end of the month": nov(30),
        "end of this month": nov(30),
        "end of month": nov(30),
        "end of next month": date(2026, 12, 31),
    })


@pytest.mark.parametrize(
    "meeting,this_week,next_week",
    [
        (nov(9), nov(13), nov(20)),    # Monday
        (nov(12), nov(13), nov(20)),   # Thursday
        (nov(13), nov(13), nov(20)),   # Friday: the end of the week is that day
        (nov(14), nov(20), nov(27)),   # Saturday: the coming week's Friday
        (nov(15), nov(20), nov(27)),   # Sunday: the same
    ],
    ids=["monday", "thursday", "friday", "saturday", "sunday"],
)
def test_the_end_of_the_week_on_a_weekday_and_at_a_weekend(meeting, this_week, next_week):
    assert resolve_due_date("end of the week", meeting) == this_week
    assert resolve_due_date("end of next week", meeting) == next_week
    assert this_week.weekday() == next_week.weekday() == FRIDAY
    assert this_week >= meeting


def test_the_end_of_the_month_and_of_next_month_across_a_year_end():
    december = date(2026, 12, 15)

    assert resolve_due_date("end of the month", december) == date(2026, 12, 31)
    assert resolve_due_date("end of next month", december) == date(2027, 1, 31)
    assert resolve_due_date("end of next month", date(2027, 1, 31)) == date(2027, 2, 28)
    assert resolve_due_date("end of next month", date(2028, 1, 31)) == date(2028, 2, 29)  # a leap year
    assert resolve_due_date("end of the month", date(2026, 12, 31)) == date(2026, 12, 31)


def test_the_end_of_a_named_month_is_the_next_one_on_or_after_the_meeting():
    check({
        "end of November": nov(30),
        "end of December": date(2026, 12, 31),
        "end of January": date(2027, 1, 31),
        "the end of January": date(2027, 1, 31),
        "end of Jan": date(2027, 1, 31),
        "end of February": date(2027, 2, 28),
        "end of October": date(2027, 10, 31),  # this year's has passed
        "end of January 2027": date(2027, 1, 31),
        "end of February 2028": date(2028, 2, 29),
    })
    assert resolve_due_date("end of January", date(2027, 1, 31)) == date(2027, 1, 31)  # on the day
    assert resolve_due_date("end of January", date(2027, 2, 1)) == date(2028, 1, 31)


# --- An absolute date ---------------------------------------------------------------------------------


def test_a_date_said_with_its_year_is_that_date():
    check({
        "2026-11-14": nov(14),
        "14/11/2026": nov(14),
        "14/11/26": nov(14),
        "4/1/2027": date(2027, 1, 4),  # day first, as written in Australia: 4 January
        "14 November 2026": nov(14),
        "14th November 2026": nov(14),
        "14th of November 2026": nov(14),
        "the 14th of November 2026": nov(14),
        "14 November, 2026": nov(14),
        "November 14, 2026": nov(14),
        "November 14th 2026": nov(14),
        "November the 14th, 2026": nov(14),
        "14 Nov 2026": nov(14),
        "the fourteenth of November 2026": nov(14),
        "3 March 2027": date(2027, 3, 3),
    })


def test_a_date_said_with_its_year_is_kept_even_when_it_is_before_the_meeting():
    """The transcript said the year, so no date is being chosen: it is copied, and a person who
    sees a deadline already past can correct it."""
    assert resolve_due_date("3 March 2026", TUESDAY) == date(2026, 3, 3)
    assert resolve_due_date("2026-11-01", TUESDAY) == nov(1)
    assert resolve_due_date("01/11/2026", TUESDAY) == nov(1)


def test_a_date_said_without_a_year_is_the_next_such_date_on_or_after_the_meeting():
    check({
        "14 November": nov(14),
        "14th November": nov(14),
        "14th of November": nov(14),
        "the 14th of November": nov(14),
        "the fourteenth of November": nov(14),
        "November 14": nov(14),
        "November 14th": nov(14),
        "November the 14th": nov(14),
        "14 Nov": nov(14),
        "14/11": nov(14),
        "10 November": nov(10),  # the meeting's own day is "on or after"
        "10/11": nov(10),
        "9 November": date(2027, 11, 9),  # yesterday's date is next year's
        "9/11": date(2027, 11, 9),
        "3 March": date(2027, 3, 3),
        "1 January": date(2027, 1, 1),
        "31 December": date(2026, 12, 31),
        "the thirty-first of January": date(2027, 1, 31),
        "the first of December": date(2026, 12, 1),
        "the twenty-second of November": nov(22),
    })


def test_a_day_of_the_month_alone_is_the_next_such_day_on_or_after_the_meeting():
    check({
        "the 14th": nov(14),
        "the 14": nov(14),
        "the fourteenth": nov(14),
        "the 10th": nov(10),
        "the 9th": date(2026, 12, 9),
        "the 1st": date(2026, 12, 1),
        "the first": date(2026, 12, 1),
        "the 30th": nov(30),
        "the 31st": date(2026, 12, 31),  # November has no 31st
        "the thirty-first": date(2026, 12, 31),
        "the twenty-eighth": nov(28),
        "the twenty eighth": nov(28),
        "the 22nd": nov(22),
        "the 23rd": nov(23),
    })
    # From 30 January, "the 30th" is that day and "the 31st" the next; "the 29th" skips to March
    # in a year whose February has 28 days.
    assert resolve_due_date("the 29th", date(2027, 1, 30)) == date(2027, 3, 29)
    assert resolve_due_date("the 29th", date(2028, 1, 30)) == date(2028, 2, 29)


def test_a_weekday_with_a_day_of_the_month_resolves_only_where_the_two_agree():
    """"Wednesday the 28th": the weekday must agree with the next 28th, or nothing is resolved.
    From Tuesday 10 November 2026 the next 28th is a Saturday; from Tuesday 20 October 2026 it is
    Wednesday 28 October."""
    assert date(2026, 11, 28).weekday() == SATURDAY and date(2026, 10, 28).weekday() == WEDNESDAY

    assert resolve_due_date("Wednesday the 28th", TUESDAY) is None
    assert resolve_due_date("Saturday the 28th", TUESDAY) == nov(28)
    assert resolve_due_date("Saturday, the 28th", TUESDAY) == nov(28)
    assert resolve_due_date("by Saturday the twenty-eighth", TUESDAY) == nov(28)
    assert resolve_due_date("Friday the 13th", TUESDAY) == nov(13)
    assert resolve_due_date("Thursday the 13th", TUESDAY) is None

    october = date(2026, 10, 20)
    assert resolve_due_date("Wednesday the 28th", october) == date(2026, 10, 28)
    assert resolve_due_date("Saturday the 28th", october) is None


@pytest.mark.parametrize(
    "phrase",
    ["30 February", "February 30", "31 April", "31/04", "31/11", "31/02/2027", "2026-02-30", "2026-13-01",
     "the 32nd", "the 0th", "32 November", "0/11", "13/14", "14/13/2026", "the thirtieth of February",
     "30 February 2027", "0000-01-01"],
)
def test_an_impossible_date_resolves_to_nothing(phrase):
    assert resolve_due_date(phrase, TUESDAY) is None


def test_a_month_first_numeric_date_is_not_reinterpreted():
    """"11/14/2026" is read day first, finds no fourteenth month, and is left unresolved: the
    rule is one reading, not whichever reading yields a date."""
    assert resolve_due_date("11/14/2026", TUESDAY) is None
    assert resolve_due_date("11/14", TUESDAY) is None


def test_the_twenty_ninth_of_february_is_never_moved_to_another_day():
    """Said in November 2026, the next 29 February is in 2028. Whether that far date is found or
    the phrase is left unresolved, the answer is never the 28th or 1 March."""
    for phrase in ("29 February", "February 29", "29/02", "the twenty-ninth of February"):
        resolved = resolve_due_date(phrase, TUESDAY)
        assert resolved is None or (resolved.month, resolved.day) == (2, 29), phrase
    assert resolve_due_date("29 February", date(2028, 1, 10)) == date(2028, 2, 29)
    assert resolve_due_date("29 February 2028", TUESDAY) == date(2028, 2, 29)


# --- Leading connectives and a trailing time of day ---------------------------------------------------


@pytest.mark.parametrize("connective", ["by", "on", "before", "due", "until", "no later than", "for",
                                        "due by", "due on", "by no later than"])
def test_a_leading_connective_does_not_change_the_date(connective):
    for phrase, expected in {
        "Friday": nov(13),
        "next Friday": nov(20),
        "the 14th": nov(14),
        "14 November": nov(14),
        "tomorrow": nov(11),
        "the end of the week": nov(13),
        "end of the month": nov(30),
    }.items():
        assert resolve_due_date(f"{connective} {phrase}", TUESDAY) == expected, f"{connective} {phrase}"


@pytest.mark.parametrize("time_of_day", ["morning", "afternoon", "evening", "night", "at the latest"])
def test_a_trailing_time_of_day_does_not_change_the_date(time_of_day):
    for phrase, expected in {
        "Friday": nov(13),
        "next Friday": nov(20),
        "tomorrow": nov(11),
        "by Friday": nov(13),
        "the 14th": nov(14),
    }.items():
        assert resolve_due_date(f"{phrase} {time_of_day}", TUESDAY) == expected, f"{phrase} {time_of_day}"


@pytest.mark.parametrize("phrase", ["next Friday", "Next Friday", "NEXT FRIDAY", "next   Friday", "  next Friday  ",
                                    "next Friday.", "next Friday,", "next Friday!", "next\tFriday", "By next Friday."])
def test_case_spacing_and_final_punctuation_do_not_change_the_date(phrase):
    assert resolve_due_date(phrase, TUESDAY) == nov(20)


# --- A time of day, wherever it sits ---------------------------------------------------------------
#
# Added on 11 November 2026, after the live development run produced "by end of day tomorrow" and
# it resolved to nothing. A time of day is ignored whether it trails the day or leads it: the day
# is what is resolved. These rows are read from Monday 14 September 2026, whose week ends on
# Friday the 18th.

MONDAY_14_SEPTEMBER = date(2026, 9, 14)


def sep(day: int) -> date:
    return date(2026, 9, day)


def test_the_second_reference_day_is_the_monday_its_rows_assume():
    assert MONDAY_14_SEPTEMBER.weekday() == MONDAY
    assert sep(18).weekday() == FRIDAY


def test_a_time_of_day_in_front_of_the_day_or_after_it_does_not_change_the_date():
    check(
        {
            # The phrase the development run produced, and its mirror image.
            "by end of day tomorrow": sep(15),
            "tomorrow by the end of the day": sep(15),
            "close of business Friday": sep(18),
            "Friday close of business": sep(18),
            "end of day Friday": sep(18),
            "by Thursday night": sep(17),
            # Said on a Monday, "Monday" is seven days on, with or without "first thing".
            "first thing Monday": sep(21),
            "first thing on Monday": sep(21),
            # The same rule in its other spellings.
            "cob Friday": sep(18),
            "Friday cob": sep(18),
            "eod tomorrow": sep(15),
            "tomorrow eod": sep(15),
            "tomorrow end of day": sep(15),
            "first thing tomorrow": sep(15),
            "by close of business tomorrow": sep(15),
            "the end of the day on Friday": sep(18),
            "Friday by close of business": sep(18),
            "close of business on the 16th": sep(16),
            "end of day next Friday": sep(25),
            "end of the day today": sep(14),
            "end of next week by close of business": sep(25),
            "end of the week at the latest": sep(18),
        },
        MONDAY_14_SEPTEMBER,
    )


def test_a_time_of_day_on_its_own_is_still_the_meetings_own_day_and_the_week_still_ends_on_friday():
    """Unchanged by the rule above: with no day beside it, "end of the day" IS the phrase."""
    check(
        {
            "end of the day": sep(14),
            "by the end of the day": sep(14),
            "end of day": sep(14),
            "by end of day": sep(14),
            "eod": sep(14),
            "cob": sep(14),
            "close of business": sep(14),
            "end of the week": sep(18),
            "by the end of the week": sep(18),
            "end of the month": sep(30),
        },
        MONDAY_14_SEPTEMBER,
    )


@pytest.mark.parametrize(
    "phrase",
    ["end of day next week", "first thing next week", "close of business soon", "end of day once finance approves",
     "first thing", "first thing after the audit", "eod this week", "close of business over the weekend",
     "end of day 30 February", "first thing the 32nd"],
)
def test_a_time_of_day_does_not_make_an_unresolved_phrase_resolve(phrase):
    """Ignoring the time of day leaves the day to be resolved by the same rules as before. Where
    those fix none, a time of day beside it fixes none either."""
    assert resolve_due_date(phrase, MONDAY_14_SEPTEMBER) is None


def test_end_of_is_not_a_connective():
    """"End of" changes the date, so it is not stripped like "by": "end of the month" is the
    30th, not whatever "the month" would resolve to."""
    assert resolve_due_date("end of the month", TUESDAY) == nov(30)
    assert resolve_due_date("the month", TUESDAY) is None


# --- What stays unresolved: a date is never invented ----------------------------------------------------

UNRESOLVED = [
    "next week", "this week", "soon", "the week after next", "over the weekend", "after the audit",
    "once finance approves", "before the move", "ASAP", "as soon as possible", "when the budget is approved",
    "next month", "this month", "next quarter", "end of the quarter", "end of the year", "end of the financial year",
    "next year", "at the next meeting", "for the next meeting", "by the next board meeting", "Friday week",
    "a week on Friday", "the Friday after next", "sometime in March", "in March", "March", "mid-December",
    "early next week", "later this week", "Q1", "TBC", "to be confirmed", "ongoing", "the first Saturday of next month",
    "Christmas", "the weekend", "end of the weekend", "end of the week after next", "14", "14th", "Friday or Monday",
    "Friday and Monday", "the 14th or the 21st", "between the 14th and the 21st", "not Friday", "every Friday",
    "this", "next", "the", "by", "end of", "?", "-",
]


@pytest.mark.parametrize("phrase", UNRESOLVED)
def test_a_phrase_the_rules_do_not_fix_resolves_to_nothing(phrase):
    """The phrase is kept on the item (``due_text``) and no date is stored: the person sees what
    was said and can set one. A guess would look exactly like a rule."""
    assert resolve_due_date(phrase, TUESDAY) is None


@pytest.mark.parametrize("phrase", ["", None, "   ", "\n", "."])
def test_no_phrase_resolves_to_nothing(phrase):
    assert resolve_due_date(phrase, TUESDAY) is None


@pytest.mark.parametrize(
    "phrase",
    # The first passes the last date there is (year 9999); the second is past what a timedelta holds.
    ["in 3000000 days", "within 99999999999 weeks"],
    ids=["past the last date", "past any timedelta"],
)
def test_a_count_too_large_for_any_date_resolves_to_nothing_and_does_not_raise(phrase):
    """The phrase is a model's copy of uploaded text. "Anything else resolves to None": a count
    that reaches past the last date there is names no date, and it must not raise, because the
    caller is the transaction that stores the whole summary (apps/meetings/summaries.py::_store),
    and one such line in a transcript would then cost the meeting its summary on every attempt.

    **This test found a defect.** As first written on 11 November 2026,
    ``m + timedelta(days=count * per)`` raised OverflowError for both, and
    apps/meetings/tests/test_summary_runs.py showed the consequence for a whole run. Fixed on 12
    November: ``resolve_due_date`` now catches a date no calendar holds and resolves it to None."""
    assert resolve_due_date(phrase, TUESDAY) is None


def test_a_large_count_that_does_name_a_date_is_still_arithmetic():
    assert resolve_due_date("in 400 days", TUESDAY) == TUESDAY + timedelta(days=400)


# --- The reference is the meeting date and nothing else ------------------------------------------------


def test_the_same_phrase_resolves_from_each_meetings_own_date():
    """Not from today: a transcript ingested years after its meeting resolves as it would have on
    the day."""
    assert resolve_due_date("tomorrow", date(2020, 2, 28)) == date(2020, 2, 29)
    assert resolve_due_date("tomorrow", date(2021, 2, 28)) == date(2021, 3, 1)
    assert resolve_due_date("next Friday", date(2019, 12, 31)) == date(2020, 1, 10)
    assert resolve_due_date("the 14th", date(1999, 12, 20)) == date(2000, 1, 14)


def year_less_phrases() -> list[str]:
    phrases = [
        "today", "tonight", "end of the day", "tomorrow", "the day after tomorrow", "in 1 day", "in 3 days",
        "within 10 days", "in a week", "in 2 weeks", "in a fortnight", "end of the week", "end of next week",
        "end of the month", "end of next month", "by Friday at the latest", "tomorrow morning",
        "by end of day tomorrow", "tomorrow by the end of the day", "close of business Friday",
        "Friday close of business", "end of day Friday", "by Thursday night", "first thing Monday", "eod", "cob",
    ]
    for name in WEEKDAYS:
        phrases += [name, f"this {name}", f"next {name}", f"{name} the 28th", f"{name} the 1st"]
    for day in range(1, 32):
        phrases += [f"the {day}", f"{day}/2", f"{day}/12", f"{day} March", f"June {day}"]
    for word in ("first", "fourteenth", "twenty-ninth", "thirtieth", "thirty-first"):
        phrases += [f"the {word}", f"the {word} of February", f"the {word} of December"]
    for month in sorted(set(MONTHS)):
        phrases += [f"end of {month}", f"1 {month}", f"{month} 15"]
    return phrases


def test_nothing_said_without_a_year_ever_resolves_to_a_day_before_the_meeting():
    """Every year-less form, from every meeting date across thirteen months that hold a leap day
    and two year ends. A deadline agreed in a meeting cannot already have passed when it was said."""
    phrases = year_less_phrases()
    first = date(2027, 12, 1)
    resolved_count = 0
    for offset in range(400):
        meeting = first + timedelta(days=offset)
        for phrase in phrases:
            resolved = resolve_due_date(phrase, meeting)
            if resolved is not None:
                resolved_count += 1
                assert resolved >= meeting, (phrase, meeting, resolved)

    assert date(2028, 2, 29) > first and date(2028, 2, 29) < first + timedelta(days=400)  # the leap day is inside
    assert resolved_count > 400 * len(phrases) // 2  # and most of these really do resolve


def test_the_end_of_the_month_is_its_last_day_from_every_day_of_two_years():
    meeting = date(2027, 1, 1)
    while meeting < date(2029, 1, 1):
        following = (meeting.year + 1, 1) if meeting.month == 12 else (meeting.year, meeting.month + 1)
        assert resolve_due_date("end of the month", meeting) == last_day(meeting.year, meeting.month), meeting
        assert resolve_due_date("end of next month", meeting) == last_day(*following), meeting
        meeting += timedelta(days=1)
