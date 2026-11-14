"""FR-11 permission-scoped retrieval: the candidate set, restricted before ranking.

This module is CLAUDE.md section 6 invariant 1, and it is the only place retrieval
decides what a user may see. The scope is a predicate on the ``content_chunks``
table itself, so the database never returns an out-of-scope row in the first place.

**Why filtering before ranking is not the same thing as filtering afterwards.**
The two orders produce the same visible list and are otherwise nothing alike. A
post-filter ranks first, which means every restricted passage has already been read
out of the store and into application memory, where it is one careless log line, one
debug response or one refactor away from the prompt sent to the AI service. Any
count, total or "showing 10 of 400" taken before the discard discloses the volume of
material the user cannot read, which is itself information about the organisation.
Filtering first means the restricted rows are never selected, so there is nothing to
leak, nothing to count and nothing to remember to discard.

**Counts.** Whatever a caller reports as a result count is computed from this
queryset's output and never from anything wider — ``scoped_chunks(...).count()``, or
the length of the ranked list derived from it. Because the excluded rows are absent
from the query rather than removed from its results, no total this queryset can
produce is capable of disclosing inaccessible content.

**Absence, not suppression.** An out-of-scope chunk is simply not there. It is not
returned marked as withheld, not counted, not greyed out and not the subject of a
distinguishing error message: retrieval cannot tell the difference between content
that does not exist and content this role may not see, and neither can the answer
(CLAUDE.md section 6 invariant 6).

The permission array lives on the chunk row itself, stamped from the owning Document
or Meeting at ingestion (D-17), so visibility is never worked out here by joining to
the source. Meetings are scoped by role exactly as documents are, never by
attendance, and ``MeetingAttendees`` is a participation record that this module does
not consult (D-16). The array holds role names (D-11). A row is in a role's scope when
its array OVERLAPS that role's effective roles, ``EFFECTIVE_ROLES`` in
apps/core/constants.py (D-66): Administrator generalises Employee in scope as well as in
permissions, so an Administrator reads everything marked for Employees, while an Employee's
effective roles are only ``Employee`` and their scope is exactly what membership of
``Employee`` gave before. An Employee never reads Administrator-only content. What
ingestion writes into the array, both roles by default, is D-29's and is not changed here.

**Until 5 October 2026 this paragraph said the opposite**: that membership of the reader's
own role was the whole test and an Administrator did not see Employee-only content. That was a
reading this build adopted, and the proposal's role model — Administrator generalising
Employee — supports the other one. It also made an Employee-only document invisible, and so
undeletable under FR-15, to every Administrator. D-66 records the change.

The candidate set is built from two predicates, both of them here and both of them
conditions on the query: the role scope above, and the embedding-model match in
``candidate_chunks`` below. The second is the risk R10 rule from
docs/ai-provider.md section 4: a chunk whose recorded ``embedding_model`` differs
from the model that embedded the question is excluded from the candidate set
entirely — not ranked lower, not down-weighted, not admitted with a caveat. Vectors
produced by two different models are not comparable, but cosine similarity over them
still returns a plausible-looking number, so a mismatch surfaces as a confidently
wrong answer rather than as an error. Nothing further down the pipeline can detect
it. Exclusion at the candidate set is what makes the corruption visible: a re-index
that has not run yet shows up as an empty result and an honest no-answer, which is
recoverable, instead of as an answer drawn from vectors that mean nothing
(``manage.py reindex`` is the intended remedy, and switching providers is a full
re-index event).
"""

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

from apps.core.constants import EFFECTIVE_ROLES, ROLE_NAMES
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting


class UnscopedRequestError(RuntimeError):
    """A scope was asked for on behalf of nobody.

    Raised rather than defaulted, because every fallback available here is a wrong
    answer: an empty scope silently returns nothing where a bug should be loud, and
    any non-empty one would hand content to a request with no authenticated user
    behind it. Routes are ``IsAuthenticated`` already (invariant 4); this is the
    backstop for a caller reached some other way.
    """


def permission_scope(user) -> str:
    """The role name this request is scoped to, re-read from the user row every time.

    Proposal 7.10 step 2 resolves the role from the session on every question rather
    than caching it from the first, "because a role changed mid-conversation must
    take effect on the next question rather than at the next sign-in". The read is
    therefore a fresh query against ``users`` joined to ``roles``, never
    ``user.role.role_name`` off an instance that may have been loaded minutes ago
    and never a value carried in the session. apps/api/permissions.py resolves the
    role per request for the same reason; this mirrors it.

    Raises UnscopedRequestError if there is no authenticated, still-existing user.
    """
    if user is None or not getattr(user, "is_authenticated", False) or user.pk is None:
        raise UnscopedRequestError("Retrieval scope requires an authenticated user.")
    role_name = (
        get_user_model()
        .objects.filter(pk=user.pk)
        .values_list("role__role_name", flat=True)
        .first()
    )
    if not role_name:
        # The row went away between authentication and this read.
        raise UnscopedRequestError("The requesting user no longer has a role.")
    return role_name


def effective_roles(role_name: str) -> tuple[str, ...]:
    """The role names whose content ``role_name`` may read (D-66); empty for an unknown role."""
    return EFFECTIVE_ROLES.get(role_name, ())


def reads_everything(role_name: str) -> bool:
    """Whether ``role_name`` has the full scope: its effective roles include every role in
    ROLE_NAMES, so it reads whatever any role reads (D-66).

    Today that is the Administrator and no other role. It is read from EFFECTIVE_ROLES and
    ROLE_NAMES rather than from a role name, so a role added later is judged by what it reads. A
    role EFFECTIVE_ROLES does not know reads nothing, so this answers False: it fails closed.
    FR-10's department scheme uses it (D-129's security review, finding F1): a hidden department
    is offered only to an audience every role of which reads everything, which needs no carrier.
    """
    return set(ROLE_NAMES) <= set(effective_roles(role_name))


def _in_scope(model, role_name: str) -> QuerySet:
    """``model``'s rows whose ``visible_to_roles`` overlaps this role's effective roles.

    The one place the FR-11 predicate is written, for chunks and sources alike (D-53). The
    overlap is a condition on the query, so an excluded row is never fetched. A role with no
    effective roles — one missing from ``EFFECTIVE_ROLES``, or renamed (D-11's stated
    limitation) — is given an empty queryset explicitly rather than a predicate that happens
    to match nothing: this fails closed, returning nothing rather than everything.
    """
    roles = list(effective_roles(role_name))
    if not roles:
        return model.objects.none()
    return model.objects.filter(visible_to_roles__overlap=roles)


def scoped_chunks(*, role_name: str) -> QuerySet[ContentChunk]:
    """Every chunk this role may see, as a queryset — the FR-11 candidate set.

    The filter is a condition on the query, so the rows excluded by it are never
    fetched. Callers narrow this further (the embedding-model predicate) and rank
    what survives; nothing downstream may widen it, and nothing downstream should
    need to re-check visibility, because no row outside the scope was ever read.

    An unknown or renamed role yields an empty queryset, and so does a chunk whose array
    is empty: this function fails closed, returning nothing rather than everything.
    """
    return _in_scope(ContentChunk, role_name)


def scoped_documents(*, role_name: str) -> QuerySet[Document]:
    """Every document this role may see: the same rule as ``scoped_chunks``, on the source row.

    For every route that returns a document's own row, its title, date or identifier: the
    repository list, the detail view, reprocess, the keyword search's document group, and
    the answer path's Sources panel and partial matches (D-53). The document's own
    ``visible_to_roles`` must overlap the role's effective roles (D-66), as a condition on
    the query, so an out-of-scope row is never fetched, and an unknown role or an empty array
    yields nothing.

    **This fails closed where a source and its chunks disagree.** D-47's cascade keeps the two
    arrays equal through every ORM write path except ``bulk_create(update_conflicts=True)``
    and raw SQL. Where they do disagree, a caller that starts here returns less than the chunk
    stamp would admit, never more. D-53 decided that direction: returning less is a usability
    defect, and returning more is a disclosure.
    """
    return _in_scope(Document, role_name)


def scoped_meetings(*, role_name: str) -> QuerySet[Meeting]:
    """Every meeting this role may see, by role and never by attendance (D-16).

    ``scoped_documents`` for meetings, failing closed in the same way. ``MeetingAttendees``
    is not consulted: it is a participation record for FR-20, and a second scoping mechanism
    would be a second code path through the one filter that matters most (invariant 3).
    """
    return _in_scope(Meeting, role_name)


def candidate_chunks(*, role_name: str, embedding_model: str) -> QuerySet[ContentChunk]:
    """The candidate set proper: in scope for this role and comparable to this query.

    Both predicates are conditions on one query, so a row failing either is never
    fetched. ``embedding_model`` is the name the provider recorded on the query's
    own EmbeddingResult, matched against the name ingestion recorded on each chunk
    from its response (apps/ingestion/embedding.py) — one value read from one place
    on both sides, never a literal and never settings.

    A mismatched chunk is excluded, not demoted: see the module docstring for why a
    number that looks like a similarity is worse here than no number at all. If the
    corpus was indexed by a model the current provider no longer serves, this
    returns nothing, and the pipeline's no-answer path is the correct and visible
    outcome until ``manage.py reindex`` has run.

    This is the whole of what ranking may see. Item 3 orders it and applies TOP_K and
    RELEVANCE_THRESHOLD; nothing downstream widens it.
    """
    return scoped_chunks(role_name=role_name).filter(embedding_model=embedding_model)
