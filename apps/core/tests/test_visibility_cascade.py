"""The invariant-2 cascade at the model level: the test CLAUDE.md says it has.

    Changing a source's visibility **re-stamps every one of its chunks in the same
    transaction** — that cascade is a model-level guarantee, not a convention, and it has
    its own test. See D-17.

This is that test, and the "model-level" half is what it is built to establish rather than
assume. Nothing here goes through a view, a serializer or a URL: the cascade is exercised by
``document.save()`` and by ``Document.objects.filter(...).update(...)``, because a guarantee
that only holds when a particular endpoint remembers to call something is the convention
invariant 2 refuses. ``apps/api/tests/test_fr11_scoping.py`` section 8 carries the
consequence at the boundary — the same change, then ``POST /api/ask`` — and the two are
deliberately separate: the boundary test would still pass if a view did the re-stamping, and
these would not.

**Both source models, the same mixin.** Documents and Meetings mirror each other exactly by
D-16, so every property below is asserted for both, parametrised over the two rather than
written twice, and a divergence between them fails here instead of appearing as a meeting
that is answerable after being restricted.

**Widening as much as narrowing.** Narrowing is the security direction; widening is the one
that gets found later, when a document restricted by mistake stays unanswerable after the
mistake is corrected and the only visible fix is a re-index of material whose vectors were
never wrong.
"""

import pytest
from django.conf import settings
from django.db import transaction

import apps.core.visibility as visibility
from apps.ai.testing import STUB_EMBEDDING_MODEL
from apps.core.constants import (
    ADMINISTRATOR_ROLE_NAME,
    EMPLOYEE_ROLE_NAME,
    SOURCE_TYPES,
)
from apps.core.models import VOCABULARY_MAX_LENGTH
from apps.documents.models import ContentChunk, Document
from apps.meetings.models import Meeting

pytestmark = pytest.mark.django_db

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES
BOTH_ROLES = [EMPLOYEE_ROLE_NAME, ADMINISTRATOR_ROLE_NAME]
ADMINISTRATOR_ONLY = [ADMINISTRATOR_ROLE_NAME]
EMPLOYEE_ONLY = [EMPLOYEE_ROLE_NAME]

EMBEDDING = [0.25] * settings.EMBEDDING_DIMENSION


def make_chunk(*, source_type, source_id, roles, index=0, text="A passage."):
    """A chunk stamped as ingestion stamps it (D-17), with a recognisable vector."""
    return ContentChunk.objects.create(
        source_type=source_type,
        source_id=source_id,
        chunk_index=index,
        chunk_text=text,
        embedding=list(EMBEDDING),
        embedding_model=STUB_EMBEDDING_MODEL,
        embedding_dimension=settings.EMBEDDING_DIMENSION,
        visible_to_roles=roles,
    )


def make_document(uploader, *, roles, chunks=2):
    document = Document.objects.create(
        title="Board remuneration review",
        file_type="pdf",
        uploaded_by=uploader,
        visible_to_roles=roles,
    )
    for index in range(chunks):
        make_chunk(
            source_type=DOCUMENT_SOURCE_TYPE,
            source_id=document.id,
            roles=roles,
            index=index,
            text=f"Document passage {index}.",
        )
    return document


def make_meeting(*, roles, chunks=2):
    meeting = Meeting.objects.create(
        title="Board in-camera session",
        meeting_date="2026-01-05",
        transcript_text="The chair recorded a loading for directors.",
        visible_to_roles=roles,
    )
    for index in range(chunks):
        make_chunk(
            source_type=MEETING_SOURCE_TYPE,
            source_id=meeting.id,
            roles=roles,
            index=index,
            text=f"Meeting passage {index}.",
        )
    return meeting


@pytest.fixture(params=["document", "meeting"])
def source(request, employee):
    """One source of each kind, visible to both roles, carrying two stamped chunks.

    Parametrised rather than duplicated so that every test below runs against a Document and
    against a Meeting, which is what D-16's "mirrors Documents exactly" has to mean in
    practice.
    """
    if request.param == "document":
        return make_document(employee, roles=BOTH_ROLES)
    return make_meeting(roles=BOTH_ROLES)


def stamps_of(source):
    """Every stamp on this source's chunks, in chunk order."""
    return list(
        ContentChunk.objects.filter(
            source_type=source.visibility_source_type, source_id=source.id
        )
        .order_by("chunk_index")
        .values_list("visible_to_roles", flat=True)
    )


# --- The cascade itself -------------------------------------------------------------------


def test_narrowing_a_source_re_stamps_every_one_of_its_chunks(source):
    """The measured bug, as a one-line reproduction: narrow, and the chunks follow.

    "Every one" is why the fixture writes two chunks. A cascade that re-stamped the first
    chunk of a source — the one a naive ``.first()`` would reach — would satisfy a
    single-chunk test and leave every real document, which has many, half restricted.
    """
    source.visible_to_roles = ADMINISTRATOR_ONLY

    source.save()

    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]


def test_widening_a_source_re_stamps_its_chunks_too(source):
    """A source restricted by mistake is answerable again once the mistake is corrected.

    The cascade is not a one-way ratchet towards narrower: it restores the condition "every
    chunk carries its source's scope", whichever direction that moves in. Without this, the
    correction would need a re-index of chunks whose vectors were never wrong.
    """
    source.visible_to_roles = ADMINISTRATOR_ONLY
    source.save()
    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]

    source.visible_to_roles = BOTH_ROLES
    source.save()

    assert stamps_of(source) == [BOTH_ROLES, BOTH_ROLES]


def test_the_cascade_moves_the_stamp_and_nothing_else(source):
    """No re-embedding. The vector, the model name, the dimension and the text are the same
    bytes afterwards, because a visibility change does not change what the passage says.

    Re-embedding here would be cost without a reason and would invite the risk R10 confusion
    the reverse way round: a re-index is what a MODEL change requires (docs/ai-provider.md
    section 4), and a scope change is not one.
    """
    before = list(
        ContentChunk.objects.filter(
            source_type=source.visibility_source_type, source_id=source.id
        )
        .order_by("chunk_index")
        .values("id", "chunk_text", "embedding_model", "embedding_dimension", "created_at")
    )
    vectors_before = [
        list(chunk.embedding)
        for chunk in ContentChunk.objects.filter(
            source_type=source.visibility_source_type, source_id=source.id
        ).order_by("chunk_index")
    ]

    source.visible_to_roles = ADMINISTRATOR_ONLY
    source.save()

    after = list(
        ContentChunk.objects.filter(
            source_type=source.visibility_source_type, source_id=source.id
        )
        .order_by("chunk_index")
        .values("id", "chunk_text", "embedding_model", "embedding_dimension", "created_at")
    )
    vectors_after = [
        list(chunk.embedding)
        for chunk in ContentChunk.objects.filter(
            source_type=source.visibility_source_type, source_id=source.id
        ).order_by("chunk_index")
    ]
    assert after == before
    assert vectors_after == vectors_before


def test_only_this_sources_chunks_are_re_stamped(source, employee):
    """The cascade is keyed on ``(source_type, source_id)`` — both halves.

    Three neighbours are planted: another source of the same kind, a source of the other
    kind, and a chunk carrying THIS source's id under the other source type. The last is the
    one that matters and the one no database could protect: ``ContentChunks.source_id`` is a
    plain UUID column with no foreign key (D-07), so nothing but the pair of columns
    distinguishes a document's chunk from a meeting's, and a cascade filtering on
    ``source_id`` alone would pass every other test in this file.
    """
    sibling = (
        make_document(employee, roles=BOTH_ROLES, chunks=1)
        if source.visibility_source_type == DOCUMENT_SOURCE_TYPE
        else make_meeting(roles=BOTH_ROLES, chunks=1)
    )
    other_kind = (
        make_meeting(roles=BOTH_ROLES, chunks=1)
        if source.visibility_source_type == DOCUMENT_SOURCE_TYPE
        else make_document(employee, roles=BOTH_ROLES, chunks=1)
    )
    impostor = make_chunk(
        source_type=(
            MEETING_SOURCE_TYPE
            if source.visibility_source_type == DOCUMENT_SOURCE_TYPE
            else DOCUMENT_SOURCE_TYPE
        ),
        source_id=source.id,  # the same identifier, the other source type
        roles=BOTH_ROLES,
        index=7,
    )

    source.visible_to_roles = ADMINISTRATOR_ONLY
    source.save()

    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]
    assert stamps_of(sibling) == [BOTH_ROLES]
    assert stamps_of(other_kind) == [BOTH_ROLES]
    impostor.refresh_from_db()
    assert impostor.visible_to_roles == BOTH_ROLES


def test_a_source_with_no_chunks_yet_saves_without_incident(employee):
    """Creation, and any save before ingestion has written a chunk, is a no-op cascade.

    Asserted because the cascade runs on every save that writes the column, including the
    INSERT: there is nothing to re-stamp yet and nothing may fail.
    """
    document = Document.objects.create(
        title="Nothing indexed yet",
        file_type="pdf",
        uploaded_by=employee,
        visible_to_roles=BOTH_ROLES,
    )

    document.visible_to_roles = ADMINISTRATOR_ONLY
    document.save()

    assert stamps_of(document) == []


# --- The same transaction -----------------------------------------------------------------


def test_a_failed_cascade_rolls_the_sources_own_change_back(source, monkeypatch):
    """"In the same transaction" is the half of invariant 2 that is easy to half-implement.

    The cascade is made to fail, and the assertion is about the SOURCE row: it must still
    carry the old scope. A ``post_save`` receiver on a save in autocommit — which is every
    ``document.save()`` outside an ``atomic()`` block — would have committed the narrowed
    source before the receiver ran, leaving the source restricted and its chunks wide: the
    exact state the cascade exists to prevent, arrived at by the cascade's own failure.
    """

    def boom(**kwargs):
        raise RuntimeError("the cascade failed")

    monkeypatch.setattr(visibility, "restamp_chunks", boom)
    source.visible_to_roles = ADMINISTRATOR_ONLY

    with pytest.raises(RuntimeError):
        source.save()

    assert type(source).objects.get(pk=source.pk).visible_to_roles == BOTH_ROLES
    assert stamps_of(source) == [BOTH_ROLES, BOTH_ROLES]


def test_the_cascade_is_inside_the_callers_transaction_when_there_is_one(source):
    """A caller's rollback takes the re-stamp with it, so an ingestion-style transaction that
    fails later cannot leave chunks stamped for a source change that never committed."""
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            source.visible_to_roles = ADMINISTRATOR_ONLY
            source.save()
            assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]
            raise RuntimeError("something later in the same unit of work failed")

    assert type(source).objects.get(pk=source.pk).visible_to_roles == BOTH_ROLES
    assert stamps_of(source) == [BOTH_ROLES, BOTH_ROLES]


# --- update_fields: the cascade mirrors what the save wrote -------------------------------


def test_a_save_that_does_not_write_the_column_does_not_re_stamp(source):
    """``save(update_fields=["status"])`` is how ingestion advances a document, and it must
    not carry a visibility change with it.

    The instance here is deliberately holding a scope it never saved — the same situation as
    an instance loaded before someone else's edit. The chunks keep the scope the SOURCE ROW
    has, which is the one the source row actually has, because the cascade mirrors the write
    rather than the instance.
    """
    source.visible_to_roles = ADMINISTRATOR_ONLY  # never saved

    source.save(update_fields=["status"])

    assert type(source).objects.get(pk=source.pk).visible_to_roles == BOTH_ROLES
    assert stamps_of(source) == [BOTH_ROLES, BOTH_ROLES]


def test_a_save_naming_the_column_in_update_fields_does_re_stamp(source):
    source.visible_to_roles = ADMINISTRATOR_ONLY

    source.save(update_fields=["visible_to_roles"])

    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]


# --- QuerySet.update(), which no save() override and no signal can reach -------------------


def test_a_queryset_update_cascades(source):
    """``objects.filter(...).update()`` is one SQL statement: no ``save()``, no signal.

    It is reachable — ``apps/api/views.py`` writes several single-column changes this way —
    so a guarantee placed only on ``save()`` would be one convenient one-liner away from
    being bypassed, and an FR-15 bulk visibility edit is the obvious caller to write it.
    """
    updated = type(source).objects.filter(pk=source.pk).update(
        visible_to_roles=ADMINISTRATOR_ONLY
    )

    assert updated == 1
    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]


def test_a_queryset_update_filtered_on_the_column_being_written_still_cascades(source):
    """The rows are identified before the UPDATE, not after.

    ``filter(visible_to_roles=BOTH).update(visible_to_roles=[Administrator])`` matches nothing
    once it has run, so a cascade that re-read the queryset afterwards would silently
    re-stamp no chunks — and this is the natural shape of a bulk edit ("everything currently
    visible to both roles becomes Administrator-only").
    """
    updated = type(source).objects.filter(visible_to_roles=BOTH_ROLES).update(
        visible_to_roles=ADMINISTRATOR_ONLY
    )

    assert updated == 1
    assert stamps_of(source) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]


def test_a_queryset_update_of_another_column_leaves_the_stamps_alone(source):
    """No cascade where the column was not written, and no wasted statement either."""
    type(source).objects.filter(pk=source.pk).update(title="Renamed")

    assert stamps_of(source) == [BOTH_ROLES, BOTH_ROLES]


def test_one_queryset_update_over_two_sources_re_stamps_both(employee):
    """A bulk edit across several sources of the same kind, since that is what a queryset
    update is for. Both documents' chunks follow, and a third source's do not."""
    first = make_document(employee, roles=BOTH_ROLES)
    second = make_document(employee, roles=BOTH_ROLES)
    untouched = make_document(employee, roles=BOTH_ROLES, chunks=1)

    updated = Document.objects.filter(pk__in=[first.pk, second.pk]).update(
        visible_to_roles=EMPLOYEE_ONLY
    )

    assert updated == 2
    assert stamps_of(first) == [EMPLOYEE_ONLY, EMPLOYEE_ONLY]
    assert stamps_of(second) == [EMPLOYEE_ONLY, EMPLOYEE_ONLY]
    assert stamps_of(untouched) == [BOTH_ROLES]


def test_a_related_manager_update_cascades_too(employee):
    """``user.uploaded_documents.update(...)`` goes through the same queryset class, so the
    reverse accessor is not a second door. Asserted rather than assumed: Django builds the
    related manager from the model's default manager, which is now the cascading one."""
    document = make_document(employee, roles=BOTH_ROLES)

    employee.uploaded_documents.update(visible_to_roles=ADMINISTRATOR_ONLY)

    assert stamps_of(document) == [ADMINISTRATOR_ONLY, ADMINISTRATOR_ONLY]


def test_a_queryset_update_reads_the_stored_scope_back_rather_than_the_argument(employee):
    """An expression, not a list: the cascade stamps what the database stored.

    ``array_remove(visible_to_roles, 'Employee')`` produces a DIFFERENT result per row, so
    there is no single value in ``kwargs`` to copy onto the chunks, and the two documents
    must end up with two different stamps. A cascade that trusted the argument would stamp
    both chunks with an SQL expression object or with one row's answer for both.
    """
    from django.contrib.postgres.fields import ArrayField
    from django.db.models import CharField, F, Func, Value

    wide = make_document(employee, roles=BOTH_ROLES, chunks=1)
    already_narrow = make_document(employee, roles=EMPLOYEE_ONLY, chunks=1)

    Document.objects.filter(pk__in=[wide.pk, already_narrow.pk]).update(
        visible_to_roles=Func(
            F("visible_to_roles"),
            Value(EMPLOYEE_ROLE_NAME),
            function="array_remove",
            output_field=ArrayField(CharField(max_length=VOCABULARY_MAX_LENGTH)),
        )
    )

    assert stamps_of(wide) == [ADMINISTRATOR_ONLY]
    assert stamps_of(already_narrow) == [[]]  # every role removed: readable by nobody
    # And the sources agree with their chunks, which is the whole condition the cascade keeps.
    assert Document.objects.get(pk=wide.pk).visible_to_roles == ADMINISTRATOR_ONLY
    assert Document.objects.get(pk=already_narrow.pk).visible_to_roles == []
