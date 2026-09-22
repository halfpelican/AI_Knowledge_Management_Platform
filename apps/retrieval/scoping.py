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
not consult (D-16). The array holds role names (D-11) and membership in it is the
whole test: an Administrator does not implicitly see Employee-scoped content, nor an
Employee Administrator-scoped content. Role generalisation is a question about
permissions (FR-05), not about ``visible_to_roles``, where the default at ingestion
is both roles (D-29).

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

from apps.documents.models import ContentChunk


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


def scoped_chunks(*, role_name: str) -> QuerySet[ContentChunk]:
    """Every chunk this role may see, as a queryset — the FR-11 candidate set.

    The filter is a condition on the query, so the rows excluded by it are never
    fetched. Callers narrow this further (the embedding-model predicate) and rank
    what survives; nothing downstream may widen it, and nothing downstream should
    need to re-check visibility, because no row outside the scope was ever read.

    A role name that matches no row in any ``visible_to_roles`` array — an unknown
    role, or a renamed one (D-11's stated limitation) — yields an empty queryset.
    That is deliberate: this function fails closed, returning nothing rather than
    everything.
    """
    return ContentChunk.objects.filter(visible_to_roles__contains=[role_name])


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
