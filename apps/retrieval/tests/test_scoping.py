"""FR-11: the permission boundary on the candidate set (CLAUDE.md invariant 1, D-17).

Role names come from apps.core.constants, never as literals, so that a rename shows
up here as a failure rather than as a test that quietly agrees with itself.
"""

import pytest
from django.conf import settings

from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import ADMINISTRATOR_ROLE_NAME, EMPLOYEE_ROLE_NAME, SOURCE_TYPES
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting
from apps.retrieval.scoping import (
    UnscopedRequestError,
    candidate_chunks,
    permission_scope,
    scoped_chunks,
    scoped_documents,
    scoped_meetings,
)

pytestmark = pytest.mark.django_db

ROLE_PAIR = (EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME)

# A corpus indexed by some other model: the risk R10 case, spelled once.
OTHER_EMBEDDING_MODEL = "some-other-model"


def make_chunk(
    document,
    visible_to_roles,
    *,
    index,
    text="Leave is approved by a manager.",
    embedding_model=STUB_EMBEDDING_MODEL,
):
    """A chunk stamped with a visibility scope, as ingestion stamps it (D-17).

    ``embedding_model`` is the name ingestion took from the provider's response, not
    a setting; the default is the stub's, since the stub is what the suite embeds
    with.
    """
    return ContentChunk.objects.create(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=index,
        chunk_text=text,
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model=embedding_model,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=visible_to_roles,
    )


@pytest.fixture
def one_chunk_per_scope(document):
    """A chunk per scope: Employee-only, Administrator-only, both, and nobody.

    The ``nobody`` row (``[]``) is what keeps an Administrator's scope tested for an
    exclusion since D-66: an Administrator reads both roles' content, so the empty array is
    the one scope left that it may not read (``apps/retrieval/tests/scopes.py``).
    """
    return {
        "employee_only": make_chunk(document, [EMPLOYEE_ROLE_NAME], index=1, text="Employee only."),
        "administrator_only": make_chunk(
            document, [ADMINISTRATOR_ROLE_NAME], index=2, text="Administrator only."
        ),
        "both": make_chunk(document, list(ROLE_PAIR), index=3, text="Everybody."),
        "nobody": make_chunk(document, [], index=4, text="Nobody."),
    }


# What each role reads of ``one_chunk_per_scope`` under D-66, written out as the premise rather
# than derived from EFFECTIVE_ROLES, so a wrong mapping fails here instead of moving with it.
READABLE_KEYS = {
    EMPLOYEE_ROLE_NAME: {"employee_only", "both"},
    ADMINISTRATOR_ROLE_NAME: {"employee_only", "administrator_only", "both"},
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


def _one_source_per_scope(uploader):
    """A document and a meeting per scope, each with one chunk stamped as its source is.

    ``nobody`` (``[]``) is the row both roles are refused, so a scope that returned every
    row would fail the tests below from either side.
    """
    scopes = {
        "employee_only": [EMPLOYEE_ROLE_NAME],
        "administrator_only": [ADMINISTRATOR_ROLE_NAME],
        "both": list(ROLE_PAIR),
        "nobody": [],
    }
    rows = {}
    for key, roles in scopes.items():
        document = Document.objects.create(
            title=f"Document {key}", file_type="pdf", uploaded_by=uploader, visible_to_roles=roles
        )
        meeting = Meeting.objects.create(
            title=f"Meeting {key}",
            meeting_date="2026-09-01",
            transcript_text="A transcript.",
            visible_to_roles=roles,
        )
        chunk = make_chunk(document, roles, index=10, text=f"Chunk {key}.")
        rows[key] = (document, meeting, chunk)
    return rows


def test_an_employees_scope_is_exactly_the_content_marked_for_employees(employee):
    """D-66 changes nothing for an Employee, by construction: their effective roles are
    ``Employee`` alone, so overlap is the membership test it replaced. This was test
    ``test_the_scope_is_symmetrical_no_role_generalisation``'s Employee half, and it holds
    unchanged — no Administrator-only or nobody's document, meeting or chunk, and every
    other one."""
    rows = _one_source_per_scope(employee)
    expected = {"employee_only", "both"}

    assert set(scoped_documents(role_name=EMPLOYEE_ROLE_NAME)) == {rows[k][0] for k in expected}
    assert set(scoped_meetings(role_name=EMPLOYEE_ROLE_NAME)) == {rows[k][1] for k in expected}
    assert set(scoped_chunks(role_name=EMPLOYEE_ROLE_NAME)) == {rows[k][2] for k in expected}


def test_an_administrators_scope_includes_every_employee_only_document_meeting_and_chunk(
    employee,
):
    """D-66: Administrator generalises Employee in scope as well as in permissions.

    Replaces ``test_the_scope_is_symmetrical_no_role_generalisation``, which asserted the
    opposite for chunks. Under that reading an Employee-only document was invisible to every
    Administrator, and FR-15's scoped-first deletion could never reach it.
    """
    rows = _one_source_per_scope(employee)
    document, meeting, chunk = rows["employee_only"]

    assert document in scoped_documents(role_name=ADMINISTRATOR_ROLE_NAME)
    assert meeting in scoped_meetings(role_name=ADMINISTRATOR_ROLE_NAME)
    assert chunk in scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME)
    # Exactly every role's content and nothing more: the nobody row is still refused, so a
    # scope that returned every row fails here as well as one that returned too little.
    expected = {"employee_only", "administrator_only", "both"}
    assert set(scoped_documents(role_name=ADMINISTRATOR_ROLE_NAME)) == {rows[k][0] for k in expected}
    assert set(scoped_meetings(role_name=ADMINISTRATOR_ROLE_NAME)) == {rows[k][1] for k in expected}
    assert set(scoped_chunks(role_name=ADMINISTRATOR_ROLE_NAME)) == {rows[k][2] for k in expected}


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
    """The result-count clause of invariant 1: a total may not disclose volume.

    Each role is counted over fewer rows than the store holds — the Employee without the
    Administrator-only and nobody rows, the Administrator without the nobody row (D-66).
    """
    assert ContentChunk.objects.count() == len(one_chunk_per_scope)  # what the store holds
    # What this role may count.
    assert scoped_chunks(role_name=role_name).count() == len(READABLE_KEYS[role_name])
    assert scoped_chunks(role_name=role_name).count() < ContentChunk.objects.count()


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
    administrator, employee_role, administrator_role, one_chunk_per_scope
):
    """The re-read is not cosmetic: the scope it returns drives the queryset.

    Demotion first, because it is the direction that withholds: an Administrator demoted to
    Employee loses the Administrator-only chunk on the next read, with the in-memory user
    left stale. Then promotion back, which under D-66 restores the Administrator-only chunk
    and KEEPS the Employee-only one — before D-66 this test asserted that a promotion lost it.
    """
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(pk=administrator.pk)

    def scope():
        return list(scoped_chunks(role_name=permission_scope(administrator)))

    as_administrator = scope()
    assert one_chunk_per_scope["administrator_only"] in as_administrator
    assert one_chunk_per_scope["employee_only"] in as_administrator

    users.update(role=employee_role)
    demoted = scope()
    assert one_chunk_per_scope["administrator_only"] not in demoted
    assert one_chunk_per_scope["employee_only"] in demoted

    users.update(role=administrator_role)
    promoted = scope()
    assert one_chunk_per_scope["administrator_only"] in promoted
    assert one_chunk_per_scope["employee_only"] in promoted
    # And the nobody row stays out in every role the user passed through.
    for visible in (as_administrator, demoted, promoted):
        assert one_chunk_per_scope["nobody"] not in visible


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
    (CLAUDE.md section 8 item 2). The Employee sees its own chunk and the shared one, and
    not the Administrator's; the Administrator sees all three, because D-66 makes it
    generalise Employee in scope. Each role is still refused a row: the Administrator-only
    one for the Employee, and the nobody row for both."""
    role_name = session_client.role_name

    assert permission_scope(session_client.user) == role_name
    visible = list(scoped_chunks(role_name=permission_scope(session_client.user)))
    assert set(visible) == {one_chunk_per_scope[key] for key in READABLE_KEYS[role_name]}
    for key in set(one_chunk_per_scope) - READABLE_KEYS[role_name]:
        assert one_chunk_per_scope[key] not in visible
    assert one_chunk_per_scope["nobody"] not in visible
    assert len(visible) == scoped_chunks(role_name=role_name).count()


# --- The second predicate: the embedding-model match (risk R10) ------------------------


@pytest.fixture
def one_chunk_per_combination(document):
    """Chunks over both predicates, so exactly one is a candidate for an Employee.

    In scope or not, embedded by the query's model or not. The FR-11 role filter and
    the risk R10 model filter are independent, and a chunk has to pass both. "In scope"
    and "out of scope" are named from the Employee's side. ``nobody_same_model`` is the row
    an Administrator is still refused since D-66: comparable, and scoped to no role.
    """
    return {
        "nobody_same_model": make_chunk(document, [], index=5, text="Nobody's, comparable."),
        "in_scope_same_model": make_chunk(
            document, [EMPLOYEE_ROLE_NAME], index=1, text="In scope, comparable."
        ),
        "in_scope_other_model": make_chunk(
            document,
            [EMPLOYEE_ROLE_NAME],
            index=2,
            text="In scope, not comparable.",
            embedding_model=OTHER_EMBEDDING_MODEL,
        ),
        "out_of_scope_same_model": make_chunk(
            document, [ADMINISTRATOR_ROLE_NAME], index=3, text="Out of scope, comparable."
        ),
        "out_of_scope_other_model": make_chunk(
            document,
            [ADMINISTRATOR_ROLE_NAME],
            index=4,
            text="Out of scope, not comparable.",
            embedding_model=OTHER_EMBEDDING_MODEL,
        ),
    }


def test_a_chunk_recorded_against_another_model_is_excluded_not_demoted(one_chunk_per_combination):
    """Risk R10: exclusion, not a lower rank.

    The distinction is the whole rule. A mismatched vector still yields a
    plausible-looking cosine score, so demoting it leaves it eligible to be the best
    thing available on a thin query and to be cited in an answer. Asserting absence
    from the candidate set — rather than a position within it — is what says the
    chunk was never a candidate at all.
    """
    candidates = list(candidate_chunks(role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL))
    mismatched = one_chunk_per_combination["in_scope_other_model"]

    assert mismatched not in candidates
    # Not merely last: it is not in the list in any position, and its text is not
    # reachable through it either.
    assert mismatched.chunk_text not in [chunk.chunk_text for chunk in candidates]
    assert candidates == [one_chunk_per_combination["in_scope_same_model"]]


def test_both_predicates_must_pass(one_chunk_per_combination):
    """Four chunks, one candidate. Failing either predicate is enough to be excluded."""
    candidates = list(candidate_chunks(role_name=EMPLOYEE_ROLE_NAME, embedding_model=STUB_EMBEDDING_MODEL))
    assert candidates == [one_chunk_per_combination["in_scope_same_model"]]
    for key in (
        "in_scope_other_model",
        "out_of_scope_same_model",
        "out_of_scope_other_model",
        "nobody_same_model",
    ):
        assert one_chunk_per_combination[key] not in candidates


# Each role's candidates from ``one_chunk_per_combination``: the comparable rows it may read.
# Under D-66 the Administrator reads the Employee's row as well as its own.
CANDIDATE_KEYS = {
    EMPLOYEE_ROLE_NAME: {"in_scope_same_model"},
    ADMINISTRATOR_ROLE_NAME: {"in_scope_same_model", "out_of_scope_same_model"},
}


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_the_candidate_count_excludes_both_kinds_of_exclusion(one_chunk_per_combination, role_name):
    """A count is computed after both filters, so it discloses neither kind of row: the
    other-model rows for both roles, the Administrator-only row for the Employee, and the
    nobody row for both."""
    assert ContentChunk.objects.count() == len(one_chunk_per_combination)  # the store
    assert candidate_chunks(role_name=role_name, embedding_model=STUB_EMBEDDING_MODEL).count() == len(
        CANDIDATE_KEYS[role_name]
    )


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_the_model_predicate_is_in_the_sql_not_applied_afterwards(role_name):
    """Same reasoning as the visible_to_roles SQL test above.

    A mismatched chunk read out of the store and dropped in Python would satisfy
    every other assertion in this file. What it could not do is keep the row out of
    the query, and only the compiled SQL can tell the two apart.
    """
    sql = str(candidate_chunks(role_name=role_name, embedding_model=STUB_EMBEDDING_MODEL).query)
    assert "embedding_model" in sql
    assert STUB_EMBEDDING_MODEL in sql
    # Both predicates in the one WHERE clause, not one of them somewhere else.
    assert "visible_to_roles" in sql


def test_a_corpus_indexed_by_a_model_the_provider_no_longer_serves_yields_nothing(
    one_chunk_per_scope,
):
    """The recoverable failure: an empty candidate set, not an answer from noise.

    Every chunk in ``one_chunk_per_scope`` is recorded against the stub's model, so
    asking with a different model must return nothing at all. manage.py reindex is
    the remedy; until it has run, the honest no-answer is the correct outcome.
    """
    assert candidate_chunks(
        role_name=EMPLOYEE_ROLE_NAME, embedding_model=OTHER_EMBEDDING_MODEL
    ).count() == 0


def test_candidates_from_both_role_sessions(session_client, one_chunk_per_combination):
    """Both predicates, from an Employee session and an Administrator session. Each role's
    candidates are exactly its comparable readable rows; neither is given an other-model
    row or the nobody row."""
    role_name = session_client.role_name
    candidates = list(
        candidate_chunks(
            role_name=permission_scope(session_client.user),
            embedding_model=STUB_EMBEDDING_MODEL,
        )
    )
    assert set(candidates) == {one_chunk_per_combination[key] for key in CANDIDATE_KEYS[role_name]}
    assert len(candidates) == len(CANDIDATE_KEYS[role_name])
    assert one_chunk_per_combination["nobody_same_model"] not in candidates


# --- The source predicates: scoped_documents and scoped_meetings (D-53) -------------------
#
# The same rule as scoped_chunks, applied to the Document and Meeting rows themselves: the
# source's own visible_to_roles overlapping the role's effective roles (D-66), as a condition
# on the query, failing closed. D-53 moved every hand-written copy of it onto these helpers.


SOURCE_HELPERS = [scoped_documents, scoped_meetings]


@pytest.mark.parametrize("helper", SOURCE_HELPERS, ids=lambda helper: helper.__name__)
@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_the_source_predicate_is_in_the_sql_not_applied_afterwards(helper, role_name):
    sql = str(helper(role_name=role_name).query)
    assert "visible_to_roles" in sql
    assert role_name in sql
    assert "WHERE" in sql.upper()


@pytest.mark.parametrize("helper", SOURCE_HELPERS, ids=lambda helper: helper.__name__)
def test_an_unknown_role_name_is_given_no_source(employee, helper):
    """Failure path: fails closed, as scoped_chunks does — nothing rather than everything."""
    _one_source_per_scope(employee)
    assert helper(role_name="Auditor").count() == 0


@pytest.mark.parametrize("role_name", ROLE_PAIR)
def test_a_source_scoped_to_nobody_is_given_to_nobody(employee, role_name):
    Document.objects.create(title="Nobody's", file_type="pdf", uploaded_by=employee, visible_to_roles=[])
    Meeting.objects.create(
        title="Nobody's", meeting_date="2026-09-01", transcript_text="A transcript.", visible_to_roles=[]
    )
    assert scoped_documents(role_name=role_name).count() == 0
    assert scoped_meetings(role_name=role_name).count() == 0
