"""Session authentication that answers 401, not 403, when there is no session.

The API authenticates with the Django session cookie (docs/decisions.md D-21).
DRF's own SessionAuthentication returns no ``WWW-Authenticate`` scheme, and DRF
downgrades NotAuthenticated to 403 whenever the first authenticator has none. That
collides with CLAUDE.md section 6 invariant 4 (401 for no valid session, 403 for a
session whose role lacks the permission), so this subclass names the scheme and
DRF keeps the 401.
"""

from rest_framework import authentication


class SessionAuthentication(authentication.SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
