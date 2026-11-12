"""FR-16's attribution rule (apps/meetings/owners.py, D-125): "a named owner is matched against
the user list, and where no confident match exists the item is stored as unassigned rather than
attributed to the wrong person."

Objective 04's third criterion is the reason every doubtful case below ends unassigned: an item
stored without an owner passes it, and an item given to the wrong person does not. So the two rules
that DO match are tested as narrowly as they are written, and everything else is tested to be None:

1. a full name that exactly one of THIS MEETING'S recorded attendees has, compared after case
   folding and collapsing spaces;
2. a lone first name that exactly one of those attendees has;

and the one attendee matched is the owner only if their role can read the meeting.

**Why attendees, and why readers** (the security review of 12 November 2026, D-125's third note).
Rule 1 used to search every user. Registration is open (FR-01), so a name in a transcript could be
claimed by registering it, and a registered namesake turned a real colleague's items unassigned.
And an owner could be given work from a meeting they cannot see. The sections "A name cannot be
claimed by registering it" and "The owner can read the meeting" hold the fix.

**Attendance narrows whose name was meant; it grants nothing** (invariant 3, D-16). The last section
holds that matching changes nothing about who may see the meeting, and that who can read it is
decided by FR-11's one scoping function, not a predicate written here.

The users are the Objective 04 roster's awkward cases: two people called Alex, two called Haddad.
"""

from __future__ import annotations

import inspect
from datetime import date
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

import apps.meetings.owners as owners
from apps.accounts.models import Role
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME
from apps.meetings.models import Meeting, MeetingAttendee
from apps.meetings.owners import OwnerDirectory, can_read_meeting, normalise_name, readers_among

pytestmark = pytest.mark.django_db

BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]


def person(name: str, *, email: str | None = None, role_name: str = EMPLOYEE_ROLE_NAME):
    """A user with no usable password: nobody signs in as these."""
    address = email or f"{'.'.join(name.lower().split())}@kmp.example"
    role = Role.objects.get(role_name=role_name)
    return get_user_model().objects.create_user(address, None, name=name, role=role)


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
    """Six Employees. Two share the first name Alex, two the surname Haddad."""
    names = ["Alex Morgan", "Alex Petrov", "Jamal Haddad", "Nadia Haddad", "Priya Raman", "Wei Zhang"]
    return {name: person(name) for name in names}


def match(meeting: Meeting, owner_name):
    return OwnerDirectory.for_meeting(meeting).match(owner_name)


# --- Rule 1: a full name that exactly one attendee has ------------------------------------------------


@pytest.mark.parametrize(
    "said",
    ["Priya Raman", "priya raman", "PRIYA RAMAN", "Priya  Raman", "  Priya Raman  ", "Priya\tRaman",
     "Priya\nRaman", "Priya Raman.", "Priya Raman,", '"Priya Raman"', "(Priya Raman)"],
)
def test_a_full_name_matches_its_one_attendee_whatever_its_case_and_spacing(roster, said):
    assert match(meeting_with(roster["Priya Raman"], roster["Wei Zhang"]), said) == roster["Priya Raman"]


def test_a_full_name_picks_between_two_attendees_who_share_a_first_name(roster):
    meeting = meeting_with(roster["Alex Morgan"], roster["Alex Petrov"])

    assert match(meeting, "Alex Petrov") == roster["Alex Petrov"]
    assert match(meeting, "Alex Morgan") == roster["Alex Morgan"]


def test_two_attendees_with_the_same_full_name_are_unassigned(roster):
    """No confident match: the name fits two people in the room."""
    namesake = person("Priya Raman", email="priya.raman.2@kmp.example")

    assert match(meeting_with(roster["Priya Raman"], namesake), "Priya Raman") is None
    assert match(meeting_with(roster["Priya Raman"], namesake), "Priya") is None


def test_a_full_name_held_by_a_user_who_was_not_recorded_as_an_attendee_is_unassigned(roster):
    """The cost of the security review's fix, held so that it stays a decision (D-125's third note):
    a task the transcript gives by full name to a colleague who was not recorded as attending is
    stored unassigned. Before 12 November it was theirs."""
    meeting = meeting_with(roster["Wei Zhang"])

    assert match(meeting, "Priya Raman") is None
    assert match(meeting_with(), "Priya Raman") is None


@pytest.mark.parametrize("said", ["Priya Ramen", "Priya R", "Priya R.", "Priya Raman-Lee", "P. Raman", "Raman Priya",
                                  "Priya Anne Raman", "PriyaRaman"])
def test_a_name_that_is_nearly_an_attendees_is_not_a_match(roster, said):
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
    assert match(here, "Priya Raman") is None
    assert match(elsewhere, "Priya") == roster["Priya Raman"]


# --- A name cannot be claimed by registering it (the security review of 12 November) ----------------


def test_registering_the_name_of_someone_the_transcript_names_claims_nothing(roster):
    """Registration is open (FR-01) and a user's name is whatever they typed. Matched against every
    user, an item given to a contractor who is not a user went to whoever registered that name."""
    claimant = person("Brendan Cole", email="not.brendan@kmp.example")
    meeting = meeting_with(roster["Priya Raman"], roster["Wei Zhang"])

    assert match(meeting, "Brendan Cole") is None
    assert match(meeting, "Brendan") is None
    assert match(meeting_with(claimant), "Brendan Cole") == claimant  # recorded attendance is what counts


def test_a_registered_namesake_takes_nothing_from_the_attendee(roster):
    """A second "Priya Raman" registered by someone else used to make the real one's items
    unassigned, since two users with one name is no confident match. Only attendees are compared now."""
    person("Priya Raman", email="priya.raman.claimant@kmp.example")
    meeting = meeting_with(roster["Priya Raman"], roster["Wei Zhang"])

    assert match(meeting, "Priya Raman") == roster["Priya Raman"]
    assert match(meeting, "Priya") == roster["Priya Raman"]


# --- The owner can read the meeting (the security review of 12 November) -----------------------------


def test_an_attendee_whose_role_cannot_read_the_meeting_is_never_the_owner(roster):
    """An Employee recorded at a meeting visible to Administrators only cannot see it, so cannot be
    given its work: the item, its passages and the meeting's title would be attributed outside the
    meeting's scope."""
    director = person("Grace Okafor", role_name=ADMINISTRATOR_ROLE_NAME)
    meeting = meeting_with(roster["Priya Raman"], director, visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    assert match(meeting, "Priya Raman") is None
    assert match(meeting, "Priya") is None
    assert match(meeting, "Grace Okafor") == director
    assert match(meeting, "Grace") == director


def test_an_administrator_attendee_can_own_an_item_from_a_meeting_marked_for_employees(roster):
    """Administrator generalises Employee in scope (D-66), so reads a meeting marked for Employees."""
    director = person("Grace Okafor", role_name=ADMINISTRATOR_ROLE_NAME)
    meeting = meeting_with(roster["Priya Raman"], director, visible_to_roles=[EMPLOYEE_ROLE_NAME])

    assert match(meeting, "Grace") == director
    assert match(meeting, "Priya") == roster["Priya Raman"]


def test_a_meeting_nobody_can_read_has_no_owner(roster):
    """An empty ``visible_to_roles`` is visible to nobody (FR-11 fails closed), so nobody owns its items."""
    director = person("Grace Okafor", role_name=ADMINISTRATOR_ROLE_NAME)
    meeting = meeting_with(roster["Priya Raman"], director, visible_to_roles=[])

    assert match(meeting, "Priya") is None
    assert match(meeting, "Grace Okafor") is None


def test_an_attendee_who_cannot_read_still_makes_a_shared_name_ambiguous(roster):
    """Who a name means is decided among everyone in the room, and only then whether they may have
    it. Two people called Alex attended; only one can read the meeting. The transcript's "Alex" may
    be the other one, so giving the item to the reader could be the wrong person: unassigned."""
    director = person("Alex Stone", role_name=ADMINISTRATOR_ROLE_NAME)
    meeting = meeting_with(roster["Alex Morgan"], director, visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    assert match(meeting, "Alex") is None
    assert match(meeting, "Alex Stone") == director
    assert match(meeting, "Alex Morgan") is None


@pytest.mark.parametrize(
    "role_name, visible_to_roles, readable",
    [
        (EMPLOYEE_ROLE_NAME, BOTH_ROLES, True),
        (EMPLOYEE_ROLE_NAME, [EMPLOYEE_ROLE_NAME], True),
        (EMPLOYEE_ROLE_NAME, [ADMINISTRATOR_ROLE_NAME], False),
        (EMPLOYEE_ROLE_NAME, [], False),
        (ADMINISTRATOR_ROLE_NAME, BOTH_ROLES, True),
        (ADMINISTRATOR_ROLE_NAME, [EMPLOYEE_ROLE_NAME], True),
        (ADMINISTRATOR_ROLE_NAME, [ADMINISTRATOR_ROLE_NAME], True),
        (ADMINISTRATOR_ROLE_NAME, [], False),
    ],
)
def test_can_read_meeting_is_fr11s_predicate_for_one_person(role_name, visible_to_roles, readable):
    """From both roles, against every visibility: the answer every route's scope would give."""
    someone = person("Sam Lee", role_name=role_name)
    meeting = meeting_with(visible_to_roles=visible_to_roles)

    assert can_read_meeting(someone, meeting) is readable


def test_attendance_does_not_make_a_meeting_readable(roster):
    """Recorded attendance is never an access rule (invariant 3): the attendee below cannot read it."""
    meeting = meeting_with(roster["Priya Raman"], visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    assert can_read_meeting(roster["Priya Raman"], meeting) is False


def test_a_role_with_no_effective_roles_reads_nothing_and_asks_the_database_nothing(django_assert_num_queries):
    """``scoped_meetings`` fails closed for a role ``EFFECTIVE_ROLES`` does not know (D-11's renamed
    role), with an empty queryset rather than a query."""
    meeting = meeting_with()
    stranger = SimpleNamespace(name="Pat Doe", role=SimpleNamespace(role_name="Contractor"))

    with django_assert_num_queries(0):
        assert readers_among([stranger], meeting) == []


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


def test_a_meeting_with_no_attendees_matches_nothing(roster):
    meeting = meeting_with()

    assert match(meeting, "Priya Raman") is None
    assert match(meeting, "Priya") is None


# --- The directory itself --------------------------------------------------------------------------------


def test_the_match_is_the_user_row_itself(roster):
    matched = match(meeting_with(roster["Priya Raman"]), "Priya")

    assert isinstance(matched, get_user_model())
    assert matched.pk == roster["Priya Raman"].pk


def test_the_names_are_read_once_and_matching_asks_the_database_nothing(roster, django_assert_num_queries):
    """Built once per summary: one read of the attendees with their roles, then one scope check per
    distinct role among them, however many items the summary holds."""
    director = person("Grace Okafor", role_name=ADMINISTRATOR_ROLE_NAME)
    meeting = meeting_with(roster["Priya Raman"], roster["Alex Morgan"])
    mixed = meeting_with(roster["Priya Raman"], roster["Alex Morgan"], director)

    with django_assert_num_queries(2):
        directory = OwnerDirectory.for_meeting(meeting)
    with django_assert_num_queries(3):
        OwnerDirectory.for_meeting(mixed)
    with django_assert_num_queries(0):
        assert directory.match("Priya") == roster["Priya Raman"]
        assert directory.match("Alex Morgan") == roster["Alex Morgan"]
        assert directory.match("Alex Petrov") is None
        assert directory.match("the facilities team") is None
        assert directory.match(None) is None


def test_the_directory_can_be_built_from_plain_lists():
    """The rules are a function of two lists, attendees and readers, with no database in them."""

    class Named:
        def __init__(self, name):
            self.name = name

    ada, grace, other_ada = Named("Ada Lovelace"), Named("Grace Hopper"), Named("Ada Yonath")

    directory = OwnerDirectory([ada, grace], readers=[ada, grace])
    assert directory.match("Ada") is ada
    assert directory.match("Grace Hopper") is grace
    assert directory.match("Ada Yonath") is None  # not an attendee
    assert directory.match("Lovelace") is None
    # Two attendees called Ada: ambiguous, whichever of them can read.
    assert OwnerDirectory([ada, grace, other_ada], readers=[ada, grace]).match("Ada") is None
    assert OwnerDirectory([ada, grace, other_ada], readers=[ada, grace]).match("Ada Yonath") is None
    # The one attendee named, who cannot read: unassigned.
    assert OwnerDirectory([ada, grace], readers=[grace]).match("Ada") is None


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


# --- Attendance narrows whose name was meant; it grants nothing (invariant 3) ----------------------------


def test_matching_an_owner_changes_nothing_about_who_may_see_the_meeting(roster):
    meeting = meeting_with(roster["Priya Raman"], visible_to_roles=[ADMINISTRATOR_ROLE_NAME])

    match(meeting, "Priya")

    meeting.refresh_from_db()
    assert meeting.visible_to_roles == [ADMINISTRATOR_ROLE_NAME]
    assert MeetingAttendee.objects.filter(meeting=meeting).count() == 1


def test_who_can_read_is_decided_by_fr11s_one_scoping_function_and_no_predicate_written_here():
    """Access narrows attribution here and nothing else does. The test of access is FR-11's own,
    ``scoped_meetings``, so this module writes no predicate of its own: not the column, not the
    overlap, not the table of effective roles (D-53's "the one place the predicate is written")."""
    source = inspect.getsource(owners)
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    code = code.replace(owners.__doc__, "")

    for forbidden in ("visible_to_roles", "overlap", "EFFECTIVE_ROLES", "effective_roles", "permission"):
        assert forbidden not in code, forbidden
    assert "scoped_meetings(role_name=" in code
    assert "attendees" in code  # and it reads the participation record for whose name was meant
