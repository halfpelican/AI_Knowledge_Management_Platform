"""FR-11: the permission boundary on the candidate set (CLAUDE.md invariant 1, D-17).

Role names come from apps.core.constants, never as literals, so that a rename shows
up here as a failure rather than as a test that quietly agrees with itself.
"""

import pytest
from django.conf import settings

from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, SOURCE_TYPES
from apps.documents.models import ContentChunk
from apps.retrieval.scoping import UnscopedRequestError, permission_scope, scoped_chunks

pytestmark = pytest.mark.django_db

ROLE_PAIR = (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)


def make_chunk(document, visible_to_roles, *, index, text="Leave is approved by a manager."):
    """A chunk stamped with a visibility scope, as ingestion stamps it (D-17)."""
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model="stub-embed",
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=visible_to_roles,
    )


@pytest.fixture
def one_chunk_per_scope(document):
    """Three chunks: Employee-only, Administrator-only, and both."""
    return {
        "employee_only": make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, text="Employee only."),
        "administrator_only": make_chunk(
            document, [ADMINISTRATOR_ROLE_NAME], index=2, text="Administrator only."
        ),
        "both": make_chunk(document, list(ROLE_PAIR), index=3, text="Everybody."),
    }


def test_an_administrator_only_chunk_is_absent_from_an_employees_scope(one_chunk_per_scope):
    employee_scope = scoped_chunks(role_name=EMPLOYEE_ROLE_NAME)
    administrator_scope = scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME)
    restricted = one_chunk_per_scope["administrator_only"]

    assert restricted not in list(employee_scope)
    assert restricted in list(administrator_scope)
    # Nothing about the restricted row reaches the Employee's candidate set: not the
    # row, not its text, not its identifier.
    assert restricted.chunk_text not in [chunk.chunk_text for chunk in employee_scope]


def test_the_scope_is_symmetrical_no_role_generalisation(one_chunk_per_scope):
    """An Administrator does not inherit Employee-only content, nor the reverse.

    Membership of visible_to_roles is the whole test (D-11, D-29). If a
    generalisation rule is ever added for FR-05 permissions, it must not reach here.
    """
    administrator_scope = list(scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME))
    assert one_chunk_per_scope["employee_only"] not in administrator_scope
    assert one_chunk_per_scope["administrator_only"] in administrator_scope


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_the_predicate_is_in_the_sql_not_applied_afterwards(role_name):
    """This is the test that distinguishes item 1 from a post-filter.

    A post-filter — rank everything, then drop what the user may not see — would
    pass every other assertion in this file, because the list it finally returns
    looks identical. What it could not do is put the permission condition in the
    query, and that is the whole of invariant 1: the restricted rows are never
    fetched, so they cannot be counted, logged or sent to the AI service. Asserting
    on the compiled SQL is the only way a test can tell the two orders apart.
    """
    sql = str(scoped_chunks(role_name=role_name).query)
    assert "visible_to_roles" in sql
    assert role_name in sql
    assert "WHERE" in sql.upper()


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_the_count_excludes_out_of_scope_chunks(one_chunk_per_scope, role_name):
    """The result-count clause of invariant 1: a total may not disclose volume."""
    assert ContentChunk.objects.count() == 3  # what the store holds
    assert scoped_chunks(role_name=role_name).count() == 2  # what this role may count


def test_a_chunk_visible_to_both_roles_is_returned_for_both(one_chunk_per_scope):
    shared = one_chunk_per_scope["both"]
    assert shared in list(scoped_chunks(role_name=EMPLOYEE_ROLE_NAME))
    assert shared in list(scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME))


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_a_chunk_scoped_to_nobody_is_returned_for_nobody(document, role_name):
    """An empty visible_to_roles is visible to no role.

    D-29 makes an empty list a 400 at upload, so one should not exist; this asserts
    what retrieval does if one ever does. It fails closed — invisible to everybody —
    rather than falling through to visible to everybody.

    The chunk is built here with an explicit ``[]`` rather than borrowed from the
    shared ``content_chunk`` fixture, which happens to be unstamped for a different
    reason (D-17: stamping is ingestion's job). A test should state its own premise,
    not inherit it from a fixture that could reasonably be stamped tomorrow.
    """
    unstamped = make_chunk(document, [], index=4, text="Scoped to nobody.")
    assert unstamped.visible_to_roles == []
    assert unstamped not in list(scoped_chunks(role_name=role_name))
    assert scoped_chunks(role_name=role_name).count() == 0


def test_an_unknown_role_name_sees_nothing(one_chunk_per_scope):
    """Failure path: a role name matching no array yields an empty candidate set."""
    assert scoped_chunks(role_name="Auditor").count() == 0


def test_permission_scope_rereads_the_role_from_the_user_row(employee, administrator_role):
    """A role changed mid-conversation takes effect on the next question (7.10 step 2).

    The user instance is deliberately left stale: the role is changed with an UPDATE
    that does not touch it, so an implementation caching user.role.role_name would
    still answer Employee here. No re-authentication, no refresh_from_db.
    """
    from django.contrib.auth import get_user_model

    assert permission_scope(employee) == EMPLOYEE_ROLE_NAME
    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)
    assert employee.role.role_name == EMPLOYEE_ROLE_NAME  # the in-memory copy is stale
    assert permission_scope(employee) == ADMINISTRATOR_ROLE_NAME


def test_permission_scope_of_a_changed_role_changes_the_candidate_set(
    employee, administrator_role, one_chunk_per_scope
):
    """The re-read is not cosmetic: the scope it returns drives the queryset."""
    from django.contrib.auth import get_user_model

    before = list(scoped_chunks(role_name=permission_scope(employee)))
    assert one_chunk_per_scope["employee_only"] in before

    get_user_model().objects.filter(pk=employee.pk).update(role=administrator_role)
    after = list(scoped_chunks(role_name=permission_scope(employee)))
    assert one_chunk_per_scope["administrator_only"] in after
    assert one_chunk_per_scope["employee_only"] not in after


def test_permission_scope_refuses_a_request_with_no_authenticated_user():
    """Failure path: no user means no scope, loudly, rather than a silent default."""
    from django.contrib.auth.models import AnonymousUser

    with pytest.raises(UnscopedRequestError):
        permission_scope(AnonymousUser())
    with pytest.raises(UnscopedRequestError):
        permission_scope(None)


def test_permission_scope_refuses_a_user_row_that_no_longer_exists(employee):
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(pk=employee.pk).delete()
    with pytest.raises(UnscopedRequestError):
        permission_scope(employee)


def test_scoping_from_both_role_sessions(session_client, one_chunk_per_scope):
    """The same test run from an Employee session and an Administrator session
    (CLAUDE.md section 8 item 2): each sees its own chunk and the shared one, and
    neither sees the other's."""
    role_name = session_client.role_name
    other_role = next(name for name in ROLE_PAIR if name != role_name)
    mine = {
        EMPLOYEE_ROLE_NAME: "employee_only",
        ADMINISTRATOR_ROLE_NAME: "administrator_only",
    }

    assert permission_scope(session_client.user) == role_name
    visible = list(scoped_chunks(role_name=permission_scope(session_client.user)))
    assert one_chunk_per_scope[mine[role_name]] in visible
    assert one_chunk_per_scope["both"] in visible
    assert one_chunk_per_scope[mine[other_role]] not in visible
    assert len(visible) == scoped_chunks(role_name=role_name).count() == 2
