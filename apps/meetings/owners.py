"""FR-16's attribution rule: "a named owner is matched against the user list, and where no
confident match exists the item is stored as unassigned rather than attributed to the wrong person"
(docs/decisions.md D-125).

The model copies an owner exactly as the transcript names them (apps/ai/summarisation.py, rule 8).
This module decides who that is on the system, by two rules and no others:

1. **A full name.** Exactly one user whose name equals the owner's, after case folding and
   collapsing spaces.
2. **A lone first name.** For an owner of one word, exactly one of THIS MEETING'S recorded
   attendees whose first name equals it. A first name is a confident match only among the people
   who were in the room: "Tom" in a transcript is far more likely an attendee than the one Tom
   among every user, and a contractor called Tom is not a user at all.

Everything else is unassigned, which is ``None`` here: no match, more than one match (two
attendees called Alex), a surname alone, a title and surname ("Ms Haddad"), two people ("Wei and
Jamal"), a team or a role ("the facilities team"), or no name. Objective 04's third criterion is
the reason for the bias: an item stored unassigned passes, and an item given to the wrong person
does not. The transcript's own words are kept on the item beside the empty owner
(``ActionItem.owner_name``), so "the facilities team" stays readable.

**Attendance is a participation record here, never an access rule** (invariant 3, D-16). Rule 2
reads ``MeetingAttendees`` to decide whose first name was meant; nothing about who may see the
meeting, its summary or its items consults it.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model


def normalise_name(value: str | None) -> str:
    """Case-folded, with surrounding punctuation gone and runs of whitespace collapsed to one space."""
    if not value:
        return ""
    return " ".join(value.casefold().strip(" \t\r\n.,;:!?\"'()").split())


class OwnerDirectory:
    """The names one meeting's owners are matched against, read once per summary."""

    def __init__(self, users, attendees):
        self._by_full_name: dict[str, list] = {}
        for user in users:
            self._by_full_name.setdefault(normalise_name(user.name), []).append(user)
        self._by_first_name: dict[str, list] = {}
        for attendee in attendees:
            words = normalise_name(attendee.name).split()
            if words:
                self._by_first_name.setdefault(words[0], []).append(attendee)

    @classmethod
    def for_meeting(cls, meeting) -> "OwnerDirectory":
        User = get_user_model()
        attendees = [record.user for record in meeting.attendees.select_related("user")]
        return cls(User.objects.only("id", "name"), attendees)

    def match(self, owner_name: str | None):
        """The one user ``owner_name`` confidently names, or None: unassigned."""
        name = normalise_name(owner_name)
        if not name:
            return None
        by_full_name = self._by_full_name.get(name, [])
        if len(by_full_name) == 1:
            return by_full_name[0]
        if by_full_name:
            return None  # two users with the same full name: no confident match
        if " " in name:
            return None  # a full name nobody has, a title and surname, two people, a team
        by_first_name = self._by_first_name.get(name, [])
        return by_first_name[0] if len(by_first_name) == 1 else None
