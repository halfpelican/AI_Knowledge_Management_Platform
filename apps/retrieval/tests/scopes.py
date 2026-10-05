"""The restricted row of a dual-role scoping test, after D-66.

Until D-66 every "from both role sessions" test hid a row stamped for whichever role was not
asking, so each role had something it could not read and neither was privileged. D-66 made
Administrator generalise Employee in scope, so an Administrator now reads every role's
content and "the other role" is no longer a scope it cannot see. Deleting the Administrator
half of those tests would leave the boundary tested from one side only, so each keeps an
exclusion: a row stamped ``[]``, visible to nobody, which no role's effective roles overlap.

Written out per role rather than derived from ``EFFECTIVE_ROLES``: derived, a mistake in that
mapping would move every test's premise along with it and nothing would fail.
"""

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME

UNREADABLE_SCOPE = {
    # The row an Employee must never read: the Administrator's.
    EMPLOYEE_ROLE_NAME: [ADMINISTRATOR_ROLE_NAME],
    # D-66: an Administrator reads both roles' content, so the only scope it cannot read is
    # the empty array.
    ADMINISTRATOR_ROLE_NAME: [],
}


def unreadable_scope(role_name: str) -> list[str]:
    """A ``visible_to_roles`` value ``role_name`` may not read. A fresh list each call."""
    return list(UNREADABLE_SCOPE[role_name])
