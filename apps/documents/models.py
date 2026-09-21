"""Documents: Documents, ExtractedContent, ContentChunks, Tags and ContentTags
(docs/schema-v1.md section 1).

The original file is stored separately from its extracted text so the text is
reusable without re-parsing (FR-08, docs/decisions.md D-05). Chunks reference their
source polymorphically, with no database foreign key (D-07), and record the model
and dimension of every stored vector (D-08, risk R10). Tags and ContentTags are in
v1 because FR-15's browse mode queries them, although FR-10 fills them later.
"""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from pgvector.django import VectorField

from apps.core.constants import (
    ACCEPTED_FORMATS,
    CLASSIFICATION_DIMENSIONS,
    DEFAULT_DOCUMENT_STATUS,
    DOCUMENT_STATUS_VALUES,
    SOURCE_TYPES,
    TAG_APPLIED_BY_VALUES,
)
from apps.core.models import (
    NAME_MAX_LENGTH,
    VOCABULARY_MAX_LENGTH,
    uuid_primary_key,
    vocabulary_field,
)


def document_upload_path(instance, filename):
    """Where an uploaded original is stored beneath MEDIA_ROOT (D-05, D-18).

    Keyed by the document's own UUID, which exists before the row is saved, so two
    uploads of ``report.docx`` never collide and the stored name stays recognisable
    for download. Django's storage sanitises ``filename`` (directory separators are
    stripped), so no upload can write outside MEDIA_ROOT.
    """
    return f"documents/{instance.id}/{filename}"


class Document(models.Model):
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

    class Meta:
        db_table = "content_tags"
