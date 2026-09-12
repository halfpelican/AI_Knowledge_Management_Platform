"""Server-side RBAC (FR-06) over the project's own tables (docs/decisions.md D-14).

``HasRolePermission.for_code("manage_roles")`` builds a DRF permission class that
passes only when the requesting user's role holds that permission in
``role_permissions``. The lookup runs on every request and nothing is cached in
the session, so a role change takes effect on the user's next request (D-21).
Combined with ``IsAuthenticated`` in front of it, an anonymous request is 401 and
an authenticated one whose role lacks the code is 403 (CLAUDE.md section 6
invariant 4). Django's Group and Permission tables are never consulted.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import RolePermission


def role_holds(role_id, permission_name: str) -> bool:
    return RolePermission.objects.filter(
        role_id=role_id, permission__permission_name=permission_name
    ).exists()


class HasRolePermission(BasePermission):
    permission_name: str | None = None

    @classmethod
    def for_code(cls, permission_name: str) -> type["HasRolePermission"]:
        return type(
            f"HasRolePermission[{permission_name}]",
            (cls,),
            {
                "permission_name": permission_name,
                "message": f"Your role does not hold the '{permission_name}' permission.",
            },
        )

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return role_holds(user.role_id, self.permission_name)
