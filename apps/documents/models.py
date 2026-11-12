"""Documents: Documents, ExtractedContent, ContentChunks, Tags, ContentTags and, since
migration v2's ``0008``, DocumentAnalysis (docs/schema-v1.md section 1).

The original file is stored separately from its extracted text so the text is
reusable without re-parsing (FR-08, docs/decisions.md D-05). Chunks reference their
source polymorphically, with no database foreign key (D-07), and record the model
and dimension of every stored vector (D-08, risk R10). Tags and ContentTags are in
v1 because FR-15's browse mode queries them; FR-10 fills them through
apps/documents/classification.py (D-105), which also writes DocumentAnalysis.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import VectorField

from apps.core.constants import (
    ACCEPTED_FORMATS,
    ASSIGNMENT_OUTCOMES,
    CLASSIFICATION_DIMENSIONS,
    DEFAULT_DOCUMENT_STATUS,
    DOCUMENT_STATUS_VALUES,
    DOCUMENT_TYPES,
    SOURCE_TYPES,
    TAG_APPLIED_BY_VALUES,
)
from apps.core.models import (
    NAME_MAX_LENGTH,
    VOCABULARY_MAX_LENGTH,
    uuid_primary_key,
    vocabulary_field,
)
from apps.core.visibility import VisibilityCascadeMixin, VisibilityCascadeQuerySet

DOCUMENT_SOURCE_TYPE, MEETING_SOURCE_TYPE = SOURCE_TYPES


def document_upload_path(instance, filename):
    """Where an uploaded original is stored beneath MEDIA_ROOT (D-05, D-18).

    Keyed by the document's own UUID, which exists before the row is saved, so two
    uploads of ``report.docx`` never collide and the stored name stays recognisable
    for download. Django's storage sanitises ``filename`` (directory separators are
    stripped), so no upload can write outside MEDIA_ROOT.
    """
    return f"documents/{instance.id}/{filename}"


class Document(VisibilityCascadeMixin, models.Model):
    """A document record. Its chunks follow its ``visible_to_roles`` (invariant 2, D-17).

    ``VisibilityCascadeMixin`` is what makes that following a property of the model: a save
    or an ``objects.update()`` that writes ``visible_to_roles`` re-stamps every
    ``ContentChunk`` of this document in the same transaction. See
    ``apps/core/visibility.py`` for why it is a ``save()`` override rather than a signal, and
    for what it deliberately does not cover.
    """

    id = uuid_primary_key("doc_id")
    title = models.CharField(max_length=NAME_MAX_LENGTH)
    # ACCEPTED_FORMATS is a set; sorted so the migration state is stable between runs.
    file_type = vocabulary_field(sorted(ACCEPTED_FORMATS))
    # The stored original. Schema v2, deferred here from v1 because its shape
    # depended on the storage decision (D-18); D-05 settles that as a local media
    # directory, so the column is a FileField. Blank only for a record that never
    # had an original retained; every FR-08 upload sets it.
    file_path = models.FileField(upload_to=document_upload_path, max_length=512, blank=True)
    # SHA-256 of the uploaded bytes. FR-08 answers 409 for a duplicate, and section
    # 7.2 compares "by content hash rather than by filename, so that the same
    # document uploaded under two different names is still caught". Unique and
    # nullable: Postgres permits many NULLs under a unique constraint, so records
    # with no stored original do not collide with each other.
    content_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="uploaded_by",
        related_name="uploaded_documents",
    )
    status = vocabulary_field(DOCUMENT_STATUS_VALUES, default=DEFAULT_DOCUMENT_STATUS)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    department = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)  # D-09
    # Role names, the proposal's shape and the FR-11 permission filter (D-11).
    visible_to_roles = ArrayField(
        models.CharField(max_length=VOCABULARY_MAX_LENGTH), default=list, blank=True
    )

    # The chunks this model is the source of, for the cascade. Declared rather than
    # inferred, so the mixin never has to guess a source type from a class name.
    visibility_source_type = DOCUMENT_SOURCE_TYPE
    # Carries the cascade to ``Document.objects.filter(...).update(visible_to_roles=...)``,
    # which no ``save()`` override and no signal can reach. ``use_in_migrations`` is false,
    # as it is for any ``as_manager()`` manager, so this adds no migration.
    objects = VisibilityCascadeQuerySet.as_manager()

    class Meta:
        db_table = "documents"

    def __str__(self):
        return self.title


class ExtractedContent(models.Model):
    id = uuid_primary_key("content_id")
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, db_column="doc_id", related_name="extracted_contents"
    )
    extracted_text = models.TextField()
    extracted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "extracted_content"


class ContentChunk(models.Model):
    id = uuid_primary_key("chunk_id")  # the identifier citation verification checks against
    source_type = vocabulary_field(SOURCE_TYPES)
    # Documents.doc_id or Meetings.meeting_id. No database FK: integrity and cascade
    # deletion are application code (D-07).
    source_id = models.UUIDField()
    chunk_index = models.PositiveIntegerField()
    chunk_text = models.TextField()
    # Sized from settings, never a literal (D-03, D-08).
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSION)
    embedding_model = models.CharField(max_length=NAME_MAX_LENGTH)
    embedding_dimension = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Same shape as Documents.visible_to_roles (docs/decisions.md D-17). The FR-11
    # permission predicate and the vector live on one table, so retrieval filters
    # before ranking structurally, not by a join it could forget. Ingestion stamps
    # it from the source, and any visibility change on a source re-stamps its chunks
    # (Stage 3 and 4 logic). No index yet.
    visible_to_roles = ArrayField(
        models.CharField(max_length=VOCABULARY_MAX_LENGTH), default=list, blank=True
    )

    class Meta:
        db_table = "content_chunks"
        indexes = [
            models.Index(fields=["source_type", "source_id"], name="content_chunks_source_idx"),
            # Retrieval filters by recorded model before ranking (risk R10).
            models.Index(fields=["embedding_model"], name="content_chunks_model_idx"),
        ]


def normalise_tag_name(value: str) -> str:
    """Strip, collapse internal whitespace to one space, lower-case."""
    return " ".join(value.split()).lower()


class Tag(models.Model):
    id = uuid_primary_key("tag_id")
    tag_name = models.CharField(max_length=NAME_MAX_LENGTH)
    dimension = vocabulary_field(CLASSIFICATION_DIMENSIONS)
    # Deactivated rather than deleted while content references it (D-12).
    active = models.BooleanField(default=True)
    # ``documents 0010``; its meaning since ``documents 0011``: not vocabulary (D-105's dated note
    # of 10 November 2026, night: the security review of ``84b5771``). A tag that is not grown is in
    # every document's scheme whatever its links; a grown one only where every audience role reads
    # a source carrying it (``tag_scheme``). Set on a tag the classifier creates or reactivates at
    # or above the threshold, in Project, Process or Topic (D-128), on one a person's confirmation
    # of a proposal creates or reactivates (``confirm_proposed_tag``, D-128), and on a Topic a
    # person's name creates or reactivates (``apply_tag``'s name form); an active tag any of them
    # fetches keeps its value, and an inactive one is reactivated only from a document every role
    # reads, else left retired (``_bring_into_use``; D-128's security review, finding 1). Also set by
    # ``documents 0011`` and the seed script's linked mode on every tag that only material some role
    # cannot read carries. A value an Administrator adds (``POST /api/tags``, D-128) is created not
    # grown: vocabulary. Never unset.
    grown = models.BooleanField(default=False)

    class Meta:
        db_table = "tags"
        constraints = [
            models.UniqueConstraint(
                fields=["tag_name", "dimension"], name="tags_unique_name_per_dimension"
            ),
        ]

    def save(self, *args, **kwargs):
        self.tag_name = normalise_tag_name(self.tag_name)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.dimension}: {self.tag_name}"


class ContentTag(models.Model):
    id = uuid_primary_key("content_tag_id")
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT, related_name="content_tags")
    source_type = vocabulary_field(SOURCE_TYPES)
    source_id = models.UUIDField()  # keyed on source type and identifier, like ContentChunks
    applied_by = vocabulary_field(TAG_APPLIED_BY_VALUES)  # provenance
    confirmed = models.BooleanField(default=False)  # a confirmed tag is not altered by reprocessing
    # FR-10 (D-105), migration v2 (``0008``). ``confidence`` is what the model reported for an
    # AI-applied link, to three places; null for a link a person applied. ``provisional`` marks
    # an AI link whose confidence was below CLASSIFICATION_CONFIDENCE_THRESHOLD: it is HELD for
    # confirmation and is not a tag of the document until ``confirm_tag`` clears it (FR-10:
    # "presented for confirmation rather than applied silently"). FR-15's readers in
    # apps/api/repository.py exclude a provisional link, and a removed one (below).
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    provisional = models.BooleanField(default=False)
    # ``documents 0009`` (D-105's dated note of 10 November 2026, night; D-119 finding 3). A person
    # removed this link, the machine's or a person's. It is no longer a tag of its document and no
    # read lists it, but the row stays, an AI link with ``confidence`` and ``provisional`` as the
    # machine set them: FR-10's correction clause keeps "the machine assignment ... alongside" the
    # person's decision, and reprocessing neither re-links nor alters it (apps/documents/
    # classification.py ``_link_tag``). A person's link was deleted on removal until the
    # requirements re-audit of ``5377e3a``, and the next run then linked the value again as the
    # machine's. ``tag_scheme`` still counts a removed link as a link, as it counts a provisional one.
    removed = models.BooleanField(default=False)

    class Meta:
        db_table = "content_tags"


class DocumentAnalysis(models.Model):
    """FR-10's record of one document's classification: one row per document (D-105).

    The proposal's field table gives DocumentAnalysis ``doc_type``, ``department``, one
    ``confidence`` and ``user_edited``. This departs from it in five places, each for a clause
    of FR-10's own text (docs/schema-v1.md section 1 records the same list):

    - **Two machine assignments, each with its own confidence.** "A confidence value is
      recorded with each assignment", and the type and the department are two assignments.
      The ``machine_*`` columns are what the model said, overwritten by every run and kept
      whatever a person decides afterwards: "the machine assignment is retained alongside it
      so that classification accuracy can be measured over time rather than being overwritten
      and lost".
    - **The effective department is ``Documents.department`` and is not duplicated here.**
      D-72 made that column the one source FR-14's and FR-15's department filters read, so the
      department FR-10 applies is written there. The effective type has no other home, so
      ``doc_type`` lives here; it is null while a provisional suggestion awaits confirmation.
    - **An outcome per assignment**, from ASSIGNMENT_OUTCOMES: how
      apps/documents/classification.py disposed of each suggestion (applied, provisional,
      discarded, confirmed), stated rather than inferred from which columns are null.
    - **Three JSON lists for suggestions that are not tags of the document**, each entry
      ``{"dimension", "value", "confidence"}`` with the normalised value.
      - ``proposed_tags``: since D-128 (12 November 2026), which departs from FR-10's controlled
        taxonomy growth clause, a value outside the scheme in Project, Process or Topic is created
        and applied when its confidence is at or above the threshold, and HELD here when it is
        below, for a person to confirm or reject. Deduplicated by dimension and value, and replaced
        by each run. The field was ``proposed_topics`` until ``documents 0012`` and keeps that column
        (``db_column``), because no migration here renames a column.
      - ``discarded_suggestions``: a value outside the scheme that may not become a Tag, whatever
        its confidence (D-128's security review, finding 2): longer than the column, more than
        MAXIMUM_CREATED_TAG_WORDS words, holding ";", or holding a control, format or surrogate
        character (Cc, Cf, Cs), recorded with each such character as U+FFFD. Replaced by each run.
        Nothing reads it as a tag and the API does not expose it. Until D-128 it held every Project
        or Process value outside the scheme, which FR-10 says is "discarded". A department outside
        the scheme is still discarded, through ``department_outcome``.
      - ``rejected_tags`` (``documents 0013``; the requirements audit of D-128, finding A5, the
        lead's decision of 13 November 2026): each proposal a person rejected on this document,
        with the machine's confidence from the proposal, so the machine assignment is kept
        alongside the person's decision (FR-10's correction clause; UC-09 A3). It is never replaced
        by a run: every later run skips each value it holds, in every dimension, at any confidence
        and before the in-scheme match (``apply_classification`` rule 4b), as it skips a value with
        a removed link on this document. A person may still apply the value. Not exposed by the
        API. Until then a rejection recorded nothing, and the next run created and linked the value
        at or above the threshold, or proposed it again below it.
    - **Whose department it is** (``department_applied_by``, ``documents 0009``): FR-10's
      provenance clause tells a machine's value from a person's, and the outcome alone cannot
      when the machine's suggestion equals the department a person typed (D-119 finding 10).

    ``user_edited`` protects a person's decision from reprocessing ("any value a user edits
    [is] retained and is not overwritten by later reprocessing"): once set, a re-run writes the
    ``machine_*`` columns, ``model``, ``input_truncated`` and ``classified_at``, and nothing
    else on this row or on ``Documents.department``.
    """

    id = uuid_primary_key("analysis_id")
    document = models.OneToOneField(
        Document, on_delete=models.CASCADE, db_column="doc_id", related_name="analysis"
    )
    # What the model said, overwritten by every run.
    machine_doc_type = vocabulary_field(DOCUMENT_TYPES, null=True, blank=True)
    machine_doc_type_confidence = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True
    )
    machine_department = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)
    machine_department_confidence = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True
    )
    # The effective type. Null while a provisional suggestion awaits confirmation.
    doc_type = vocabulary_field(DOCUMENT_TYPES, null=True, blank=True)
    doc_type_outcome = vocabulary_field(ASSIGNMENT_OUTCOMES, null=True, blank=True)
    department_outcome = vocabulary_field(ASSIGNMENT_OUTCOMES, null=True, blank=True)
    # Who supplied the department the document carries, in the tags' provenance vocabulary
    # (``documents 0009``; D-119 finding 10). ``department_outcome`` says how the machine's
    # suggestion was disposed of; this says whose value ``Documents.department`` holds, which the
    # outcome cannot: "applied" is recorded both when a run wrote its suggestion into a blank
    # department and when the suggestion merely equalled the department the uploader typed.
    #   "user"  a person gave it: typed at upload, or written through the confirm route;
    #   "ai"    a run wrote its suggestion into a blank department, and no person has written
    #           the department since (a person confirming that value keeps "ai", as a confirmed
    #           AI tag keeps ``applied_by="ai"``);
    #   null    the document has no department, or the row was classified before 0009 and no
    #           run or confirmation has set it since.
    # Written by apps/documents/classification.py wherever it decides the department.
    department_applied_by = vocabulary_field(TAG_APPLIED_BY_VALUES, null=True, blank=True)
    user_edited = models.BooleanField(default=False)
    # [{"dimension": "Project"|"Process"|"Topic", "value": <normalised name>, "confidence": <float>}]:
    # the values outside the scheme the run held below the threshold (D-128), replaced by each run.
    # Renamed from ``proposed_topics`` by ``documents 0012``; the column keeps its name.
    proposed_tags = models.JSONField(default=list, blank=True, db_column="proposed_topics")
    # [{"dimension": ..., "value": ..., "confidence": ...}], replaced by each run: since D-128 only a
    # value outside the scheme that may not become a Tag. That is one longer than a tag name, with
    # more than MAXIMUM_CREATED_TAG_WORDS words, holding ";", or holding a Cc, Cf or Cs character,
    # recorded as U+FFFD (D-128's security review, finding 2; classification.py ``_may_become_a_tag``).
    discarded_suggestions = models.JSONField(default=list, blank=True)
    # [{"dimension": ..., "value": <normalised name>, "confidence": <the proposal's>}]: each proposal a
    # person rejected on this document, deduplicated by dimension and value and never replaced by a
    # run, which skips each of them (rule 4b). ``documents 0013``; the requirements audit of D-128,
    # finding A5. Not exposed by the API. A rejection made before 0013 was never recorded, because the
    # old ``reject_proposed_tag`` wrote nothing, so it is not honoured: 0013 fills existing rows with
    # ``[]`` and none is guessed, as D-105 left the rows from before 0009.
    rejected_tags = models.JSONField(default=list, blank=True)
    model = models.CharField(max_length=NAME_MAX_LENGTH, blank=True)
    input_truncated = models.BooleanField(default=False)
    # Set explicitly by each run, never auto_now: a confirmation edits the row without
    # reclassifying it, and the timestamp must keep saying when the machine last ran.
    classified_at = models.DateTimeField()

    class Meta:
        db_table = "document_analysis"

    def __str__(self):
        return f"analysis of {self.document_id}"
