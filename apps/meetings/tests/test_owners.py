"""FR-16's attribution rule (apps/meetings/owners.py, D-125): "a named owner is matched against
the user list, and where no confident match exists the item is stored as unassigned rather than
attributed to the wrong person."

Objective 04's third criterion is the reason every doubtful case below ends unassigned: an item
stored without an owner passes it, and an item given to the wrong person does not. So the two rules
that DO match are tested as narrowly as they are written, and everything else is tested to be None:

1. a full name that exactly one user has, compared after case folding and collapsing spaces;
2. a lone first name that exactly one of THIS MEETING'S recorded attendees has.

**Attendance is used here as a participation record and for nothing else** (invariant 3, D-16).
The last section holds that: the match is the same whatever the meeting's ``visible_to_roles``,
and this module does not read that column at all.

The users are the Objective 04 roster's awkward cases: two people called Alex, two called Haddad.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest
from django.contrib.auth import get_user_model

import apps.meetings.owners as owners
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
from apps.meetings.models import Meeting, MeetingAttendee
from apps.meetings.owners import OwnerDirectory, normalise_name

pytestmark = pytest.mark.django_db

BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]


def person(name: str, *, email: str | None = None):
    """A user with no usable password: nobody signs in as these."""
    address = email or f"{'.'.join(name.lower().split())}@kmp.example"
    return get_user_model().objects.create_user(address, None, name=name)


def meeting_with(*attendees, visible_to_roles=None) -> Meeting:
    meeting = Meeting.objects.create(
        title="Level four fit-out",
        meeting_date=date(2026, 11, 10),
        transcript_text="Alex: I'll chase the fit-out quote.",
        visible_to_roles=BOTH_ROLES if visible_to_roles is None else visible_to_roles,
    )
    MeetingAttendee.objects.bulk_create([MeetingAttendee(meeting=meeting, user=user) for user in attendees])
    return meeting


@pytest.fixture
def roster():
    """Six users. Two share the first name Alex, two the surname Haddad."""
    names = ["Alex Morgan", "Alex Petrov", "Jamal Haddad", "Nadia Haddad", "Priya Raman", "Wei Zhang"]
    return {name: person(name) for name in names}


def match(meeting: Meeting, owner_name):
    return OwnerDirectory.for_meeting(meeting).match(owner_name)


# --- Rule 1: a full name that exactly one user has ------------------------------------------------


@pytest.mark.parametrize(
    "said",
    ["Priya Raman", "priya raman", "PRIYA RAMAN", "Priya  Raman", "  Priya Raman  ", "Priya\tRaman",
     "Priya\nRaman", "Priya Raman.", "Priya Raman,", '"Priya Raman"', "(Priya Raman)"],
)
def test_a_full_name_matches_its_one_user_whatever_its_case_and_spacing(roster, said):
    assert match(meeting_with(), said) == roster["Priya Raman"]


def test_a_full_name_matches_a_user_who_did_not_attend(roster):
    """Rule 1 is "matched against the user list": a task given to a named colleague who was not in
    the room is still theirs."""
    meeting = meeting_with(roster["Wei Zhang"])

    assert match(meeting, "Priya Raman") == roster["Priya Raman"]


def test_a_full_name_picks_between_two_people_who_share_a_first_name(roster):
    meeting = meeting_with(roster["Alex Morgan"], roster["Alex Petrov"])

    assert match(meeting, "Alex Petrov") == roster["Alex Petrov"]
    assert match(meeting, "Alex Morgan") == roster["Alex Morgan"]


def test_two_users_with_the_same_full_name_are_unassigned(roster):
    """No confident match: the name fits two accounts, and attending does not settle it."""
    namesake = person("Priya Raman", email="priya.raman.2@kmp.example")
    meeting = meeting_with(roster["Priya Raman"])

    assert match(meeting, "Priya Raman") is None
    assert match(meeting_with(namesake), "Priya Raman") is None
    assert match(meeting_with(), "priya raman") is None


@pytest.mark.parametrize("said", ["Priya Ramen", "Priya R", "Priya R.", "Priya Raman-Lee", "P. Raman", "Raman Priya",
                                  "Priya Anne Raman", "PriyaRaman"])
def test_a_name_that_is_nearly_a_users_is_not_a_match(roster, said):
    """Exact after case and spacing, and nothing looser: no initials, no closest spelling."""
    assert match(meeting_with(roster["Priya Raman"]), said) is None


# --- Rule 2: a lone first name, among this meeting's attendees --------------------------------------


@pytest.mark.parametrize("said", ["Priya", "priya", "PRIYA", " Priya ", "Priya.", "Priya,"])
def test_a_lone_first_name_matches_the_one_attendee_who_has_it(roster, said):
    meeting = meeting_with(roster["Priya Raman"], roster["Wei Zhang"])

    assert match(meeting, said) == roster["Priya Raman"]


def test_a_lone_first_name_held_by_a_user_who_did_not_attend_is_unassigned(roster):
    """Exactly one user is called Priya, and she was not in the room: "Priya" in this transcript
    may be someone who is not a user at all."""
    meeting = meeting_with(roster["Wei Zhang"])

    assert match(meeting, "Priya") is None
    assert match(meeting_with(), "Priya") is None


def test_a_lone_first_name_is_matched_among_attendees_even_where_another_user_shares_it(roster):
    """Two users are called Alex; one attended. In this meeting "Alex" is the one in the room."""
    meeting = meeting_with(roster["Alex Morgan"], roster["Priya Raman"])

    assert match(meeting, "Alex") == roster["Alex Morgan"]
    assert match(meeting_with(roster["Alex Petrov"]), "Alex") == roster["Alex Petrov"]


def test_two_attendees_with_the_same_first_name_are_unassigned(roster):
    """Rule 8 of the prompt forbids the model choosing one of two people; this forbids the
    application doing it."""
    meeting = meeting_with(roster["Alex Morgan"], roster["Alex Petrov"], roster["Priya Raman"])

    assert match(meeting, "Alex") is None
    assert match(meeting, "alex") is None
    assert match(meeting, "Priya") == roster["Priya Raman"]  # the others are unaffected


def test_attendance_at_another_meeting_does_not_count(roster):
    elsewhere = meeting_with(roster["Priya Raman"])
    here = meeting_with(roster["Wei Zhang"])

    assert match(here, "Priya") is None
    assert match(elsewhere, "Priya") == roster["Priya Raman"]


# --- Everything else is unassigned --------------------------------------------------------------------


@pytest.mark.parametrize("said", ["Raman", "raman", "Haddad", "Morgan", "Zhang"])
def test_a_surname_alone_is_unassigned(roster, said):
    """Even with one such attendee: a surname is not rule 2's first name, and "Haddad" is two people."""
    meeting = meeting_with(roster["Priya Raman"], roster["Jamal Haddad"], roster["Alex Morgan"], roster["Wei Zhang"])

    assert match(meeting, said) is None


@pytest.mark.parametrize("said", ["Ms Haddad", "Mr Haddad", "Ms Raman", "Dr Priya Raman", "Mrs Delaney", "Ms. Raman"])
def test_a_title_and_a_name_are_unassigned(roster, said):
    meeting = meeting_with(roster["Priya Raman"], roster["Nadia Haddad"])

    assert match(meeting, said) is None


@pytest.mark.parametrize("said", ["Wei and Jamal", "Wei & Jamal", "Wei, Jamal", "Wei/Jamal", "Wei or Jamal",
                                  "Priya Raman and Wei Zhang", "Wei with Jamal"])
def test_two_people_are_unassigned(roster, said):
    """One owner or none: an item is not given to the first of two names."""
    meeting = meeting_with(roster["Wei Zhang"], roster["Jamal Haddad"], roster["Priya Raman"])

    assert match(meeting, said) is None


@pytest.mark.parametrize("said", ["the facilities team", "Facilities", "the Finance team", "Finance", "everyone",
                                  "all of us", "the chair", "IT", "someone", "whoever is free", "Northgate Fitouts",
                                  "Brendan", "Sam"])
def test_a_team_a_role_or_someone_who_is_not_a_user_is_unassigned(roster, said):
    meeting = meeting_with(*roster.values())

    assert match(meeting, said) is None


@pytest.mark.parametrize("said", [None, "", "   ", "\n", ".", "?", "..."])
def test_no_name_is_unassigned(roster, said):
    assert match(meeting_with(*roster.values()), said) is None


def test_a_first_name_is_never_completed_into_another_full_name(roster):
    """"Alex Smith" names nobody on the system. That one Alex attended does not make it him."""
    meeting = meeting_with(roster["Alex Morgan"])

    assert match(meeting, "Alex Smith") is None
    assert match(meeting, "Alex M") is None
    assert match(meeting, "Alex from Finance") is None


def test_a_meeting_with_no_users_at_all_matches_nothing():
    meeting = meeting_with()

    assert match(meeting, "Priya Raman") is None
    assert match(meeting, "Priya") is None


# --- The directory itself --------------------------------------------------------------------------------


def test_the_match_is_the_user_row_itself(roster):
    matched = match(meeting_with(roster["Priya Raman"]), "Priya")

    assert isinstance(matched, get_user_model())
    assert matched.pk == roster["Priya Raman"].pk


def test_the_names_are_read_once_and_matching_asks_the_database_nothing(roster, django_assert_num_queries):
    """Built once per summary: one read of the users, one of the attendees, however many items
    the summary holds."""
    meeting = meeting_with(roster["Priya Raman"], roster["Alex Morgan"])

    with django_assert_num_queries(2):
        directory = OwnerDirectory.for_meeting(meeting)
    with django_assert_num_queries(0):
        assert directory.match("Priya") == roster["Priya Raman"]
        assert directory.match("Alex Petrov") == roster["Alex Petrov"]
        assert directory.match("the facilities team") is None
        assert directory.match(None) is None


def test_the_directory_can_be_built_from_plain_lists():
    """The rules are a function of two lists of names, with no database in them."""

    class Named:
        def __init__(self, name):
            self.name = name

    ada, grace, other_ada = Named("Ada Lovelace"), Named("Grace Hopper"), Named("Ada Yonath")
    directory = OwnerDirectory([ada, grace, other_ada], attendees=[ada, grace])

    assert directory.match("Ada") is ada  # one attendee called Ada, though two users are
    assert directory.match("Ada Yonath") is other_ada
    assert directory.match("Grace Hopper") is grace
    assert directory.match("Yonath") is None
    assert OwnerDirectory([ada, grace, other_ada], attendees=[ada, other_ada]).match("Ada") is None


@pytest.mark.parametrize(
    "said,normalised",
    [
        ("Priya Raman", "priya raman"),
        ("  PRIYA   RAMAN ", "priya raman"),
        ("Priya\tRaman\n", "priya raman"),
        ('"Priya Raman."', "priya raman"),
        ("Priya", "priya"),
        ("O'Brien", "o'brien"),  # punctuation inside a name is the name's
        ("Jean-Luc Picard", "jean-luc picard"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("...", ""),
    ],
)
def test_a_name_is_compared_case_folded_with_its_spaces_collapsed(said, normalised):
    assert normalise_name(said) == normalised


# --- Attendance is a participation record, never an access rule (invariant 3) ----------------------------


@pytest.mark.parametrize("visible_to_roles", [BOTH_ROLES, [EMPLOYEE_ROLE_NAME], [ADMINISTRATOR_ROLE_NAME], []],
                         ids=["both", "employee-only", "administrator-only", "nobody"])
def test_the_match_is_the_same_whatever_the_meetings_visibility(roster, visible_to_roles):
    """Who may SEE a meeting has no part in whose name was said in it. An Employee who attended an
    Administrator-only meeting is still the "Priya" its transcript names; being matched gives her
    no access to it, which apps/api/tests/test_meeting_action_items.py holds from the other side."""
    meeting = meeting_with(roster["Priya Raman"], roster["Alex Morgan"], visible_to_roles=visible_to_roles)

    assert match(meeting, "Priya") == roster["Priya Raman"]
    assert match(meeting, "Alex Petrov") == roster["Alex Petrov"]
    assert match(meeting, "Wei") is None


def test_matching_an_owner_changes_nothing_about_who_may_see_the_meeting(roster):
    meeting = meeting_with(roster["Priya Raman"], visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    match(meeting, "Priya")

    meeting.refresh_from_db()
    assert meeting.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    assert MeetingAttendee.objects.filter(meeting=meeting).count() == 1


def test_the_module_never_reads_a_visibility_column_or_a_scope():
    """Rule 2 reads ``MeetingAttendees`` to decide whose first name was meant. Nothing about
    access is decided here, so nothing about access may be read here: not the column, not the
    scoping functions, not a role."""
    source = inspect.getsource(owners)
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    code = code.replace(owners.__doc__, "")

    for forbidden in ("visible_to_roles", "scoped_", "permission_scope", "role_name", ".role", "retrieval"):
        assert forbidden not in code, forbidden
    assert "attendees" in code  # and it does read the participation record
