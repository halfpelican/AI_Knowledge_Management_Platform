"""FR-16's attribution rule: "a named owner is matched against the user list, and where no
confident match exists the item is stored as unassigned rather than attributed to the wrong person"
(docs/decisions.md D-125).

The model copies an owner exactly as the transcript names them (apps/ai/summarisation.py, rule 8).
This module decides who that is on the system.

**An owner is one of this meeting's recorded attendees, and one whose role can read the meeting.**
The name is matched among the attendees by two rules and no others:

1. **A full name.** Exactly one attendee whose name equals the owner's, after case folding and
   collapsing spaces.
2. **A lone first name.** For an owner of one word, exactly one attendee whose first name equals
   it.

The one attendee matched is then the owner only if their role can read the meeting; otherwise the
item is unassigned. The order matters. Who a name means is decided among everyone in the room, so
two attendees called Alex stay ambiguous even where only one of them can read the meeting: the
transcript's "Alex" may be the other one, and giving the item to the reader would be the wrong
person. Whether that person may be given it is decided afterwards, by scope.

**Why the candidates are narrower than every user** (the security review of 12 November 2026,
D-125's third note). Until then rule 1 searched every user, and two things followed:

- **A name could be claimed by registering it.** Registration is open (FR-01) and a user's name is
  whatever they typed. An item naming someone who is not a user, a contractor say, went to whoever
  registered that name first; and registering a real colleague's name turned that colleague's
  items unassigned, since two users with one name is no confident match. Attendees are recorded by
  the person who ingests the transcript (FR-09), so nobody can add themselves to this list.
- **An owner could be given work from a meeting they cannot see.** The item, its passages and the
  meeting's title would be attributed to someone outside the meeting's scope. So the owner must be
  able to read the meeting, decided by role through ``scoped_meetings``: the same predicate every
  route reads by (FR-11, D-66). ``can_read_meeting`` applies the same test to an owner a person
  chooses by hand (apps/api/serializers.py).

The cost is stated rather than hidden: a task the transcript gives by full name to a colleague who
was not recorded as an attendee is now stored unassigned, with the transcript's words kept beside
it, where before it was theirs.

Everything else is unassigned, which is ``None`` here: no match, more than one match (two
attendees called Alex), a surname alone, a title and surname ("Ms Haddad"), two people ("Wei and
Jamal"), a team or a role ("the facilities team"), or no name. Objective 04's third criterion is
the reason for the bias: an item stored unassigned passes, and an item given to the wrong person
does not. The transcript's own words are kept on the item beside the empty owner
(``ActionItem.owner_name``), so "the facilities team" stays readable.

**Attendance is a participation record here, never an access rule** (invariant 3, D-16). It
narrows whose name a transcript can mean; it never widens who may see the meeting. The scope check
runs the other way round: access narrows attribution, and attribution grants no access.
"""

from __future__ import annotations

from apps.retrieval.scoping import scoped_meetings


def normalise_name(value: str | None) -> str:
    """Case-folded, with surrounding punctuation gone and runs of whitespace collapsed to one space."""
    if not value:
        return ""
    return " ".join(value.casefold().strip(" \t\r\n.,;:!?\"'()").split())


def readers_among(users, meeting) -> list:
    """The users in ``users`` whose role can read ``meeting``, in the order given.

    One scope query per distinct role among them, and none at all for a role with no effective
    roles, which ``scoped_meetings`` gives an empty queryset (it fails closed). Each user's
    ``role`` should be loaded with it (``select_related``).
    """
    can_read: dict[str, bool] = {}
    readers = []
    for user in users:
        role_name = user.role.role_name
        if role_name not in can_read:
            can_read[role_name] = scoped_meetings(role_name=role_name).filter(pk=meeting.pk).exists()
        if can_read[role_name]:
            readers.append(user)
    return readers


def can_read_meeting(user, meeting) -> bool:
    """Whether ``user``'s role can read ``meeting``: FR-11's predicate, for one person."""
    return bool(readers_among([user], meeting))


class OwnerDirectory:
    """One meeting's attendees, and which of them can read it, read once per summary."""

    def __init__(self, attendees, *, readers):
        self._readers = list(readers)
        self._by_full_name: dict[str, list] = {}
        self._by_first_name: dict[str, list] = {}
        for attendee in attendees:
            name = normalise_name(attendee.name)
            if not name:
                continue
            self._by_full_name.setdefault(name, []).append(attendee)
            self._by_first_name.setdefault(name.split()[0], []).append(attendee)

    @classmethod
    def for_meeting(cls, meeting) -> "OwnerDirectory":
        attendees = [record.user for record in meeting.attendees.select_related("user__role")]
        return cls(attendees, readers=readers_among(attendees, meeting))

    def match(self, owner_name: str | None):
        """The one attendee ``owner_name`` confidently names, if they can read the meeting; else None."""
        name = normalise_name(owner_name)
        if not name:
            return None
        # A name with a space is a full name (rule 1). A full name no attendee has, a title and
        # surname, two people and a team all find nothing here; a full name two attendees share
        # finds two. A name of one word is a first name (rule 2).
        found = (self._by_full_name if " " in name else self._by_first_name).get(name, [])
        if len(found) != 1:
            return None
        return found[0] if found[0] in self._readers else None
