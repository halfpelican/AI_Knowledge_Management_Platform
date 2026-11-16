"""FR-15's document repository: the one scoped list query, browse's filters, sort and facets,
and the detail view's extracted text and tags.

**One scoped query function for both list routes (D-72).** ``GET /api/documents`` and
``GET /api/documents/browse`` build their documents with ``repository_documents``: the first
with no filters and the default sort, the second with the caller's. So the list is implemented
once, and the two routes cannot drift into disagreeing about what a caller may see or in what
order. It starts from ``scoped_documents`` (D-53), so every document either route returns, and
every number browse derives from them, is taken after the permission filter (FR-11, invariant 1).

**Facets come from the scoped documents, never from the ``Tags`` table (D-72).** Each
dimension's values and counts are computed over the documents in the caller's scope that match
every active filter except that dimension's own:

- Department from the ``documents.department`` column, the source FR-14 uses (D-70, D-72);
- Project, Process and Topic from the ``ContentTags`` rows whose ``source_id`` is one of those
  documents, joined to their ``Tag`` for its name and dimension.

A value used only on documents the caller cannot see is therefore never offered and never
counted, and a ``Tag`` row that nothing links to is never offered at all.

**The text filter reuses D-71's matching** from ``apps/retrieval/search.py``: the title and the
term each have every run of whitespace collapsed to one space, so a title that wraps a line is
found by the phrase typed on one. ``_collapsed`` is that module's private helper and is imported
rather than rewritten here, so there is one definition of the collapse.

**Every document or tag row read here is reached through a scoped document.** This module is in
``apps/api``, so ``apps/api/tests/test_source_rows_fail_closed.py`` scans it: it reads no
``Document`` manager at all. ``ContentTag`` and ``ExtractedContent`` are read only for documents
already in the caller's scope, which is what D-53's implementation note asks of FR-15's readers.

**What the filters are not.** Each value has passed ``DocumentBrowseQuerySerializer`` (D-65):
a status and a sort from their fixed vocabularies, a department and tag names for shape only.
Nothing here checks whether a department or tag exists, so an unknown value and one used only
on restricted documents match the same nothing.

**A provisional link is not a tag (FR-10, D-105).** ``ContentTag.provisional`` marks an AI
suggestion held below CLASSIFICATION_CONFIDENCE_THRESHOLD for confirmation. ``tags_of``, the tag
filters and the tag facets read ``provisional=False`` only, so a held suggestion is neither shown
as a tag, offered as a facet value nor matched by a filter until a person confirms it.
``tag_details_of`` is where it is seen, provisional included, for the detail view.

**Nor is a removed one (D-105's dated note of 10 November 2026, night).** ``ContentTag.removed``
marks a link a person removed, the machine's or a person's. It is kept for FR-10's correction
clause: an AI link so that the machine's assignment survives beside the person's decision, and a
person's so that a later classify or reprocess neither links the value again nor proposes it.
Every read here excludes it, ``tag_details_of`` included: removed is gone, as far as any screen is
concerned.
"""

from dataclasses import dataclass, fields

from django.db.models import Count, F
from django.db.models.functions import Lower

from apps.core.constants import (
    DEFAULT_DOCUMENT_SORT,
    DESCENDING_SORT_PREFIX,
    REPOSITORY_TAG_DIMENSIONS,
    SOURCE_TYPES,
)
from apps.documents.models import ContentTag, DocumentAnalysis
from apps.retrieval.scoping import scoped_documents
from apps.retrieval.search import _collapsed, collapse_whitespace

DOCUMENT_SOURCE_TYPE = SOURCE_TYPES[0]

# The query parameter, the facet key and the detail view's ``tags`` key for each tag dimension:
# the dimension's name in lower case, as docs/api-contract.md writes them.
TAG_PARAMETERS = {dimension.lower(): dimension for dimension in REPOSITORY_TAG_DIMENSIONS}
DEPARTMENT = "department"
TEXT = "q"
STATUS = "status"
# The four browse dimensions, in the contract's order: one facet each.
FACET_NAMES = (DEPARTMENT, *TAG_PARAMETERS)

# Each sort key's expression. The title sorts case-insensitively, so "budget memo" sits between
# "Annual report" and "Contract terms" whatever the database's collation does with case. The
# uploader sorts by address, the value the document object shows. The primary key breaks ties.
_SORT_EXPRESSIONS = {
    "title": Lower("title"),
    "file_type": F("file_type"),
    "uploaded_by": F("uploaded_by__email"),
    "uploaded_at": F("uploaded_at"),
    "status": F("status"),
}


@dataclass(frozen=True)
class RepositoryFilters:
    """The filters a browse request applies, each ``None`` when not applied.

    ``sort`` is not here: it is not a filter, and it never causes a 204 (D-72).
    """

    q: str | None = None
    status: str | None = None
    department: str | None = None
    project: str | None = None
    process: str | None = None
    topic: str | None = None

    @property
    def active(self) -> bool:
        """Whether any filter is set: the condition under which an empty result is a 204."""
        return any(getattr(self, field.name) is not None for field in fields(self))


NO_FILTERS = RepositoryFilters()


@dataclass(frozen=True)
class BrowseResult:
    documents: list
    facets: dict


def repository_documents(*, role_name: str, filters: RepositoryFilters = NO_FILTERS,
                         sort: str = DEFAULT_DOCUMENT_SORT):
    """The documents a role may see, filtered and sorted: the one list query (D-72).

    ``GET /api/documents`` calls this with no filters and ``DEFAULT_DOCUMENT_SORT``, which is
    newest first with the primary key breaking ties, the order that route has always
    returned. Browse calls it with the caller's filters and sort.
    """
    return _sorted(_filtered(_scoped(role_name), filters), sort)


def browse(*, role_name: str, filters: RepositoryFilters, sort: str) -> BrowseResult | None:
    """Browse's documents and facets, or ``None`` when a filter is set and nothing matches.

    ``None`` is the 204 (FR-15: "204 No Content for a filter combination with no accessible
    matches"). It needs at least one filter: with none, there is no combination to fail, so an
    empty repository is an ordinary result with empty lists (D-72). The facets are not computed
    for a 204, which has no body to carry them.
    """
    documents = list(repository_documents(role_name=role_name, filters=filters, sort=sort))
    if filters.active and not documents:
        return None
    scoped = _scoped(role_name)
    facets = {
        name: _facet(name, _filtered(scoped, filters, omit=name)) for name in FACET_NAMES
    }
    return BrowseResult(documents=documents, facets=facets)


def extracted_text_of(document) -> str | None:
    """The document's extracted text from ``ExtractedContent``, or ``None`` with no row (D-63).

    Read through the document the caller's scoped lookup resolved, never reassembled from its
    chunks: chunks overlap, and are a derived form of this text rather than the text.

    **More than one row.** ``ExtractedContent.document`` is a plain foreign key, so a document
    could hold several rows. No shipped path leaves more than one: ingestion writes one per run,
    and ``reprocess_document`` deletes the previous rows before it runs again. Should there be
    more, the newest by ``extracted_at`` is shown, which is the row ``manage.py reindex``
    re-embeds from, so the detail view shows the text the document's chunks were built from.
    The primary key breaks a tie so the choice is stable between reads.
    """
    return (
        document.extracted_contents.order_by("-extracted_at", "pk")
        .values_list("extracted_text", flat=True)
        .first()
    )


def tags_of(document) -> dict[str, list[str]]:
    """The document's APPLIED tag names in each of Project, Process and Topic, sorted and distinct.

    Every dimension is present, with an empty list where the document has none, so the shape
    does not change from one document to the next. Department is not here: it is the document's
    ``department`` field (D-72). A provisional link is not here either (D-105): it is held for
    confirmation, not applied, and ``tag_details_of`` is where it shows. A removed link is in
    neither.
    """
    tags = {parameter: [] for parameter in TAG_PARAMETERS}
    rows = (
        ContentTag.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.pk,
            tag__dimension__in=REPOSITORY_TAG_DIMENSIONS,
            provisional=False,
            removed=False,
        )
        .values_list("tag__dimension", "tag__tag_name")
        .distinct()
        .order_by("tag__dimension", "tag__tag_name")
    )
    for dimension, name in rows:
        tags[dimension.lower()].append(name)
    return tags


def classification_of(document):
    """The document's ``DocumentAnalysis``, or ``None`` where it has never been classified (D-105).

    Read through the document the caller's scoped lookup resolved, as ``extracted_text_of`` is.
    """
    return DocumentAnalysis.objects.filter(document_id=document.pk).first()


def tag_details_of(document):
    """Every ``ContentTag`` link of the document in Project, Process and Topic, provisional
    included and removed excluded, with its ``Tag`` loaded, ordered by dimension, then name, then
    primary key.

    The detail view's ``tag_details`` (D-105): where a held suggestion is seen, with its
    provenance, so a person can accept or remove it. Unlike ``tags_of`` this is one entry per
    LINK, so a document linked twice to one tag shows two entries with two ids. A link a person
    removed is kept in the table, an AI link for the machine's assignment and a person's so that no
    later run links it again, and is not one of them.
    """
    return (
        ContentTag.objects.filter(
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.pk,
            tag__dimension__in=REPOSITORY_TAG_DIMENSIONS,
            removed=False,
        )
        .select_related("tag")
        .order_by("tag__dimension", "tag__tag_name", "pk")
    )


# --- The query, in parts ---------------------------------------------------------------------


def _scoped(role_name: str):
    return scoped_documents(role_name=role_name).select_related("uploaded_by")


def _tagged(dimension: str, name: str):
    """The identifiers of documents carrying the tag ``name`` in ``dimension``, as a subquery.

    It ranges over every ``ContentTag`` row, but it is only ever an ``id__in`` condition on a
    queryset that starts from ``scoped_documents``, so the documents it can select are the
    caller's and no others, and no tag row is returned from it.
    """
    return ContentTag.objects.filter(
        source_type=DOCUMENT_SOURCE_TYPE, tag__dimension=dimension, tag__tag_name=name,
        provisional=False,  # a held suggestion is not a tag (D-105)
        removed=False,  # nor is one a person removed
    ).values("source_id")


def _filtered(documents, filters: RepositoryFilters, *, omit: str | None = None):
    """``documents`` narrowed by every active filter, combined with AND, except ``omit``.

    ``omit`` names the dimension whose facet is being computed, so that dimension's
    alternatives stay visible with the count each would leave (D-72).
    """
    if filters.q is not None:
        documents = documents.annotate(collapsed_title=_collapsed("title")).filter(
            collapsed_title__icontains=collapse_whitespace(filters.q)
        )
    if filters.status is not None:
        documents = documents.filter(status=filters.status)
    if filters.department is not None and omit != DEPARTMENT:
        # An exact match on the stored value, as FR-14's department filter is (D-70).
        documents = documents.filter(department=filters.department)
    for parameter, dimension in TAG_PARAMETERS.items():
        name = getattr(filters, parameter)
        if name is not None and omit != parameter:
            documents = documents.filter(id__in=_tagged(dimension, name))
    return documents


def _sorted(documents, sort: str):
    descending = sort.startswith(DESCENDING_SORT_PREFIX)
    expression = _SORT_EXPRESSIONS[sort.removeprefix(DESCENDING_SORT_PREFIX)]
    return documents.order_by(expression.desc() if descending else expression.asc(), "pk")


def _facet(name: str, documents) -> list[dict]:
    """One dimension's values over ``documents``, each with its count, sorted by value.

    A count is the number of distinct documents carrying the value, so a document linked to
    the same tag twice is counted once. A value with no document is absent rather than zero,
    because only values found on the documents are read at all.
    """
    if name == DEPARTMENT:
        rows = (
            documents.exclude(department="")
            .values("department")
            .annotate(count=Count("id", distinct=True))
            .order_by("department")
            .values_list("department", "count")
        )
    else:
        rows = (
            ContentTag.objects.filter(
                source_type=DOCUMENT_SOURCE_TYPE,
                source_id__in=documents.values("id"),
                tag__dimension=TAG_PARAMETERS[name],
                provisional=False,  # a held suggestion is not offered as a value (D-105)
                removed=False,  # nor is one a person removed
            )
            .values("tag__tag_name")
            .annotate(count=Count("source_id", distinct=True))
            .order_by("tag__tag_name")
            .values_list("tag__tag_name", "count")
        )
    return [{"value": value, "count": count} for value, count in rows]
