"""FR-10's taxonomy clause, administered: the Tags inventory, adding a value, and retiring a tag
(D-119 finding 5; D-128).

FR-10: "Tags are deactivated rather than deleted where content still references them, preserving
historical classification", and its CRUD line gives Tags "Create, Read, Delete". Until D-105's dated
note of 10 November 2026 (night) only the schema held the first (``Tag.active``, and ``PROTECT`` on
``ContentTag.tag``, D-12) and nothing performed either.

- ``tag_inventory()``: every Tag in REPOSITORY_TAG_DIMENSIONS with the number of sources that carry
  it, for ``GET /api/tags``.
- ``create_tag(dimension, name)``: ``POST /api/tags`` (D-128). An Administrator adds a value to the
  established scheme, UC-09's precondition ("The classification scheme is defined and holds at least
  one term against each of its dimensions"). It is created **not grown**: vocabulary, offered in
  every document's ``tag_options`` and listed in every classification prompt, as a seeded value is.
  A name that already exists in the dimension, active or retired, is ``TagAlreadyExists``, the 409.
- ``retire_tag(tag_id)``: ``DELETE /api/tags/{id}``. A tag any ``ContentTag`` row references, in any
  state, is deactivated and kept; one nothing references is deleted.

**Only an Administrator calls these** (``manage_tags``, accounts 0008, checked by the routes before
anything else). That is what lets the inventory list every tag and count every source without a
scope, and what lets the 409 name the existing tag: an Administrator reads every source (D-66), and
the inventory lists retired tags, so neither discloses anything to the one role that may ask.
``apps/accounts/tests/test_manage_tags_seed.py`` holds that every role given the code has the
Administrator's scope, as FR-19's seed test does for its log (the security review's L3).

**What deactivating does, and does not, do.** An inactive tag leaves ``tag_scheme``, which reads
active tags only, so neither the machine nor a person can newly apply it by id. Its existing links
stay, and FR-15's reads do not consult ``Tag.active`` (D-72's clarification of 7 October): a retired
tag still shows on the documents that carry it, as a facet value and as a filter. That is FR-10's
"preserving historical classification". **Retiring no longer keeps a value out of classification**
(D-128): a person who types a retired Topic's name reactivates it (``apply_tag``), a person who
confirms a proposal of a retired value reactivates it (``confirm_proposed_tag``), and so does the
classifier when it suggests a retired value at or above the threshold, in Project, Process or Topic,
each answering exactly as for a new value rather than saying that the name exists. Each brings it
back grown, **but only from a document every role can read** (D-128's security review, finding 1):
on a document some role cannot read the value is linked and stays retired, since reactivating it
there would let an old readable carrier offer it again to readers who saw nothing change.
``create_tag`` never reactivates one (D-105's note: "Declined: a route that only reactivates").

It lives beside ``classification.py`` and ``deletion.py`` in ``apps/documents``, outside the
request-serving packages D-53's scan watches; it reads no Document or Meeting row.
"""

from collections import Counter

from django.db import IntegrityError, transaction

from apps.core.constants import REPOSITORY_TAG_DIMENSIONS
from apps.documents.models import ContentTag, Tag, normalise_tag_name


class TagAlreadyExists(Exception):
    """``create_tag``'s name is already a Tag in its dimension, active or retired: FR-10 Responses,
    "409 Conflict on a duplicate tag name within a dimension". ``tag_id`` is that Tag, which the
    Administrator, the only caller, can already see in the inventory (retired ones included)."""

    def __init__(self, tag_id):
        super().__init__("A tag with this name already exists in this dimension.")
        self.tag_id = tag_id


def tag_inventory() -> list[Tag]:
    """Every Tag in REPOSITORY_TAG_DIMENSIONS, ordered by dimension then name, each carrying
    ``item_count``: the number of distinct sources, documents and meetings alike, with a link to it
    that is neither provisional nor removed. A held suggestion is not yet a tag of its source, and a
    removed one no longer is (D-105), so neither counts; a source linked twice counts once."""
    tags = list(Tag.objects.filter(dimension__in=REPOSITORY_TAG_DIMENSIONS).order_by("dimension", "tag_name"))
    counts = item_counts([tag.pk for tag in tags])
    for tag in tags:
        tag.item_count = counts.get(tag.pk, 0)
    return tags


def item_counts(tag_ids) -> Counter:
    """``{tag_id: number of distinct (source_type, source_id) with a live link}`` for ``tag_ids``."""
    pairs = (
        ContentTag.objects.filter(tag_id__in=tag_ids, provisional=False, removed=False)
        .values_list("tag_id", "source_type", "source_id")
        .distinct()
    )
    return Counter(tag_id for tag_id, _, _ in pairs)


def create_tag(dimension: str, name: str) -> Tag:
    """Add ``name`` to ``dimension`` as vocabulary (D-128): active, **not grown**, carrying
    ``item_count`` 0, since nothing links a tag just made.

    ``name`` is normalised here as well as by the route's serializer, so the check and the row
    agree on one spelling. Raises ``ValueError`` for a dimension outside REPOSITORY_TAG_DIMENSIONS
    (the route's serializer refuses one first), and ``TagAlreadyExists`` with the existing tag's id
    when a Tag of that normalised name is already in the dimension, **active or retired**. Nothing is
    changed then: a retired tag is not reactivated (D-105's note: "Declined: a route that only
    reactivates"), and ``grown`` is never unset.

    **A concurrent create of the same name** is the same ``TagAlreadyExists``: the insert runs in a
    savepoint, and the unique constraint ``tags_unique_name_per_dimension`` makes the second insert
    wait for the first and then fail, after which the committed row is read back for its id.
    """
    if dimension not in REPOSITORY_TAG_DIMENSIONS:
        raise ValueError(f"{dimension!r} is not one of {REPOSITORY_TAG_DIMENSIONS}.")
    name = normalise_tag_name(name)

    def existing_id():
        return (
            Tag.objects.filter(dimension=dimension, tag_name=name)
            .values_list("pk", flat=True)
            .first()
        )

    found = existing_id()
    if found is not None:
        raise TagAlreadyExists(found)
    try:
        with transaction.atomic():
            tag = Tag.objects.create(tag_name=name, dimension=dimension, active=True, grown=False)
    except IntegrityError:
        found = existing_id()
        if found is None:  # not the unique constraint: a defect, not a duplicate
            raise
        raise TagAlreadyExists(found)
    tag.item_count = 0
    return tag


def retire_tag(tag_id) -> Tag | None:
    """Deactivate the tag if anything references it, else delete it; one transaction.

    Returns the tag, now inactive and carrying ``item_count``, when it was kept, and None when it
    was deleted. Raises ``Tag.DoesNotExist`` for an id that names no Tag in
    REPOSITORY_TAG_DIMENSIONS, the dimensions the inventory lists and a person or the machine can
    link: a Department tag is not one of them (D-72).

    **Any reference keeps it**, provisional and removed links included: ``ContentTag.tag`` is
    ``PROTECT`` (D-12), and a removed link is kept precisely so that the machine's assignment
    survives (D-105), which deleting its tag would make impossible. A tag already inactive and still
    referenced is answered the same way again.

    **The Tag row is locked first** (``FOR UPDATE``). A link another request commits before the
    check is seen by it, and keeps the tag. A link another request has inserted but not committed is
    not seen; that request's deferred foreign-key check then waits on this lock and, once the tag is
    deleted, fails at its commit. The rare loser is that request, answered 500, and never a deleted
    tag with a link left pointing at it.
    """
    with transaction.atomic():
        tag = (
            Tag.objects.select_for_update()
            .filter(pk=tag_id, dimension__in=REPOSITORY_TAG_DIMENSIONS)
            .first()
        )
        if tag is None:
            raise Tag.DoesNotExist(f"No tag {tag_id} in {REPOSITORY_TAG_DIMENSIONS}.")
        if ContentTag.objects.filter(tag=tag).exists():
            if tag.active:
                tag.active = False
                tag.save(update_fields=["active"])
            tag.item_count = item_counts([tag.pk]).get(tag.pk, 0)
            return tag
        tag.delete()
        return None
