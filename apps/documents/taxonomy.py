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
"preserving historical classification". **A retired value comes back only through a person, on a
document every role can read**: a person who types a retired Topic's name reactivates it
(``apply_tag``), and so does a person who confirms a proposal of a retired value
(``confirm_proposed_tag``). Each answers exactly as for a new value rather than saying that the name
exists, and each brings it back grown. On a document some role cannot read the value is linked and
stays retired, since reactivating it there would let an old readable carrier offer it again to
readers who saw nothing change (D-128's security review, finding 1). The classifier never brings
one back: since D-129 a retired value it suggests is proposed (a Topic) or discarded (a Project or
Process). From D-128 until D-129 it reactivated one at or above the threshold.
``create_tag`` never reactivates one (D-105's note: "Declined: a route that only reactivates").

**The department list** (D-129, the lead's decision of 13 November 2026): the fourth dimension of
FR-10's scheme, on the same page and behind the same code. ``Department`` is a table of its own,
which keeps case (its docstring says why).

- ``department_inventory()``: every Department, active or not, ordered by name ignoring case, with
  the number of documents whose ``department`` equals the name ignoring case, for
  ``GET /api/departments``.
- ``create_department(name)``: ``POST /api/departments``. A new name is created active and **not
  grown**, vocabulary, as ``create_tag`` creates a value. An active name that exists ignoring case is
  ``DepartmentAlreadyExists``, the 409. **A retired one is reactivated**, keeping its ``grown`` and its
  spelling, which ``create_tag`` never does for a tag: a tag comes back through a person naming it
  on a document, and a department has no such path, so this is its only way back, and only an
  Administrator, who reads every document (D-66), can take it.
- ``retire_department(department_id)``: ``DELETE /api/departments/{id}``. A department any document
  uses is deactivated and kept; one no document uses is deleted.

**"Uses" and the counts compare ignoring case**, ``Lower`` on both sides in the database, as the
unique constraint compares names (D-129's security review, finding F3). Compared exactly, a hidden
department whose remaining documents spell it in another case counted as unused, was deleted, and
could be added again as vocabulary, losing its hidden marking.

Retiring or deleting a department never touches ``Documents.department``: FR-14's and FR-15's
filters read that column (D-72), so a retired department stays on its documents and in the filters.

It lives beside ``classification.py`` and ``deletion.py`` in ``apps/documents``, outside the
request-serving packages D-53's scan watches. The tag functions read no Document or Meeting row. The
department functions count documents by ``department``, unscoped, which is safe for the same reason
the tag inventory's counts are: only a holder of ``manage_tags`` calls them.
"""

from collections import Counter
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Count, Value
from django.db.models.functions import Lower

from apps.core.constants import REPOSITORY_TAG_DIMENSIONS
from apps.documents.models import (
    ContentTag,
    Department,
    Document,
    Tag,
    normalise_department_name,
    normalise_tag_name,
)


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


# --- The department list (D-129) -----------------------------------------------------------------


class DepartmentAlreadyExists(Exception):
    """``create_department``'s name is already an ACTIVE Department, ignoring case: the 409.
    ``department_id`` is that Department, which the Administrator, the only caller, already sees in
    the inventory."""

    def __init__(self, department_id):
        super().__init__("A department with this name is already listed.")
        self.department_id = department_id


@dataclass(frozen=True)
class AddedDepartment:
    """What ``create_department`` did: the Department, carrying ``item_count``, and whether it is a
    new row (the route's 201) or a retired one reactivated (its 200)."""

    department: Department
    created: bool


def documents_using(name: str) -> int:
    """The number of documents whose ``department`` equals ``name`` ignoring case: ``Lower`` on both
    sides, in the database, as the unique constraint compares names (finding F3). A document whose
    department differs in spacing is not counted. Unscoped: see the module docstring."""
    return (
        Document.objects.alias(folded=Lower("department"))
        .filter(folded=Lower(Value(name)))
        .count()
    )


def department_item_counts() -> dict[str, int]:
    """``{lower(department): number of documents}`` over every document with a department, lowered by
    the database, for ``department_inventory`` to read by each name's own database ``lower()``."""
    rows = (
        Document.objects.exclude(department="")
        .annotate(folded=Lower("department"))
        .values("folded")
        .annotate(documents=Count("pk"))
    )
    return {row["folded"]: row["documents"] for row in rows}


def department_inventory() -> list[Department]:
    """Every Department, active or not, ordered by name ignoring case, each carrying ``item_count``:
    the documents whose department equals its name ignoring case (``department_item_counts``)."""
    departments = list(
        Department.objects.annotate(folded=Lower("name")).order_by(Lower("name"), "name")
    )
    counts = department_item_counts()
    for department in departments:
        department.item_count = counts.get(department.folded, 0)
    return departments


def _department_named(name: str) -> Department | None:
    """The Department whose name equals ``name`` ignoring case, locked ``FOR UPDATE``, or None.

    Compared with ``Lower`` on both sides, in the database, exactly as the unique constraint
    ``departments_unique_name_ignoring_case`` compares names, so this finds the row an insert of
    ``name`` would collide with, and no other."""
    return (
        Department.objects.select_for_update()
        .alias(folded=Lower("name"))
        .filter(folded=Lower(Value(name)))
        .first()
    )


def create_department(name: str) -> AddedDepartment:
    """Add ``name`` to the department list, or bring a retired department back (D-129).

    ``name`` is normalised here as well as by the route's serializer (stripped, internal whitespace
    collapsed, the case kept), so the check and the row agree on one spelling. Raises ``ValueError``
    for a name that normalises to nothing, which the serializer refuses first.

    - **No department of that name, ignoring case:** created active and **not grown**, vocabulary,
      offered in every document's classification prompt whatever its audience. ``created`` is True.
    - **An active one:** ``DepartmentAlreadyExists`` with its id; nothing changes.
    - **A retired one:** reactivated, ``created`` False. Its ``grown`` is kept (never unset), and so
      is its spelling: documents and FR-15's filters carry that spelling, and a name that differs
      only in case is the same department. ``create_tag`` answers 409 for a retired tag instead,
      because a retired tag comes back when a person names it on a document every role reads; a
      department has no such path, so this is the only way back, and only an Administrator, who
      reads every document (D-66), can take it.

    ``item_count`` is set on the Department returned, and may be above 0 for a new one: a
    department typed at upload is on its documents before it is listed.

    **A concurrent create of the same name** is the same ``DepartmentAlreadyExists``: the insert runs
    in a savepoint, the unique constraint makes the second insert wait for the first and then fail,
    and the committed row is read back. The existing row is locked first (``_department_named``),
    so a concurrent retire or reactivation of it waits.
    """
    name = normalise_department_name(name)
    if not name:
        raise ValueError("A department name must have at least one character.")
    with transaction.atomic():
        department = _department_named(name)
        if department is None:
            try:
                with transaction.atomic():
                    department = Department.objects.create(name=name, active=True, grown=False)
            except IntegrityError:
                department = _department_named(name)
                if department is None:  # not the unique constraint: a defect, not a duplicate
                    raise
            else:
                department.item_count = documents_using(name)
                return AddedDepartment(department=department, created=True)
        if department.active:
            raise DepartmentAlreadyExists(department.pk)
        department.active = True
        department.save(update_fields=["active"])
        department.item_count = documents_using(department.name)
        return AddedDepartment(department=department, created=False)


def retire_department(department_id) -> Department | None:
    """Deactivate the department if any document uses it, else delete it; one transaction.

    "Uses" is ``Documents.department`` equal to the name ignoring case (``documents_using``; D-129's
    security review, finding F3), so a hidden department whose remaining documents spell it
    "PROJECTS" is retired, keeping its ``grown``, and not deleted.
    Returns the department, inactive and carrying ``item_count``, when it was kept, and None when it
    was deleted. A department already inactive and still used is answered the same way again.
    Raises ``Department.DoesNotExist`` for an id that names no Department.

    **Documents are never touched.** A retired department stays on its documents and in FR-14's and
    FR-15's filters (D-72); it leaves every scheme, since ``tag_scheme`` reads active departments
    only. The Department row is locked first (``FOR UPDATE``). There is no foreign key from a
    document to a department, so a document written with the name while this runs keeps it either
    way: if the department is deleted meanwhile, that document's department is merely unlisted,
    the state FR-08's free-text upload field can always produce.
    """
    with transaction.atomic():
        department = Department.objects.select_for_update().filter(pk=department_id).first()
        if department is None:
            raise Department.DoesNotExist(f"No department {department_id}.")
        documents = documents_using(department.name)
        if documents:
            if department.active:
                department.active = False
                department.save(update_fields=["active"])
            department.item_count = documents
            return department
        department.delete()
        return None
