"""Documents, ExtractedContent, ContentChunks, Tags, ContentTags and Departments.

FR-08, FR-10, FR-11, FR-15 and docs/decisions.md D-07, D-08, D-11, D-12, D-129.
"""

import uuid

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, transaction
from django.db.models import ProtectedError

from apps.core.constants import (
    ACCEPTED_FORMATS,
    CLASSIFICATION_DIMENSIONS,
    DEFAULT_DOCUMENT_STATUS,
    DOCUMENT_STATUS_VALUES,
    EMPLOYEE_ROLE_NAME,
    SOURCE_TYPES,
    TAG_APPLIED_BY_VALUES,
)
from apps.documents.models import ContentChunk, ContentTag, Department, Document, ExtractedContent, Tag

pytestmark = pytest.mark.django_db


def choices_of(model, field_name):
    return [choice for choice, _ in model._meta.get_field(field_name).choices]


# --- Documents and ExtractedContent -------------------------------------------------


def test_document_vocabularies_come_from_the_constants():
    assert choices_of(Document, "status") == list(DOCUMENT_STATUS_VALUES)
    assert set(choices_of(Document, "file_type")) == set(ACCEPTED_FORMATS)
    assert Document._meta.get_field("status").default == DEFAULT_DOCUMENT_STATUS


def test_new_document_starts_processing_and_visible_to_the_named_roles(document):
    document.refresh_from_db()
    assert document.status == DEFAULT_DOCUMENT_STATUS == "Processing"
    assert document.visible_to_roles == [EMPLOYEE_ROLE_NAME]
    assert document.department == ""
    assert document.uploaded_at is not None
    document.full_clean()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("status", "Bogus"), ("status", "uploaded"), ("file_type", "exe"), ("file_type", "PDF")],
)
def test_document_rejects_a_value_outside_the_vocabulary(document, field_name, value):
    setattr(document, field_name, value)
    with pytest.raises(ValidationError) as excinfo:
        document.full_clean()
    assert field_name in excinfo.value.error_dict


def test_extracted_content_cascades_with_its_document(document):
    ExtractedContent.objects.create(document=document, extracted_text="Leave requests need approval.")
    document.delete()
    assert ExtractedContent.objects.count() == 0


# --- ContentChunks -----------------------------------------------------------------


def test_content_chunk_stores_a_vector_sized_from_settings(content_chunk):
    content_chunk.refresh_from_db()
    assert len(content_chunk.embedding) == settings.EMBEDDING_DIMENSION
    assert content_chunk.embedding_dimension == settings.EMBEDDING_DIMENSION
    assert content_chunk.embedding_model == "stub-embed"
    assert choices_of(ContentChunk, "source_type") == list(SOURCE_TYPES)


def test_content_chunk_rejects_a_vector_of_the_wrong_length(document):
    chunk = ContentChunk(
        source_type=SOURCE_TYPES[0],
        source_id=document.id,
        chunk_index=0,
        chunk_text="text",
        embedding=[0.0] * (settings.EMBEDDING_DIMENSION + 1),
        embedding_model="other-model",
        embedding_dimension=settings.EMBEDDING_DIMENSION + 1,
    )
    # pgvector 0.5.0's VectorField does not validate length in full_clean(); the
    # vector(N) column does, and that is the guarantee retrieval relies on.
    with pytest.raises(DataError), transaction.atomic():
        chunk.save()


def test_content_chunk_visible_to_roles_mirrors_documents(content_chunk, document):
    # D-17: same shape as Documents.visible_to_roles, empty until ingestion stamps it.
    content_chunk.refresh_from_db()
    assert content_chunk.visible_to_roles == []
    chunk_field = ContentChunk._meta.get_field("visible_to_roles")
    document_field = Document._meta.get_field("visible_to_roles")
    assert chunk_field.base_field.max_length == document_field.base_field.max_length
    assert chunk_field.default is list and document_field.default is list
    content_chunk.visible_to_roles = [EMPLOYEE_ROLE_NAME]
    content_chunk.save()
    assert ContentChunk.objects.get(pk=content_chunk.pk).visible_to_roles == [EMPLOYEE_ROLE_NAME]
    assert ContentChunk.objects.filter(visible_to_roles__contains=[EMPLOYEE_ROLE_NAME]).count() == 1


def test_content_chunk_source_is_not_a_database_foreign_key(content_chunk, document):
    # D-07: the database accepts a dangling source_id and does not cascade; the
    # application deletes chunks with their source, in the same transaction.
    ContentChunk.objects.create(
        source_type=SOURCE_TYPES[1],
        source_id=uuid.uuid4(),
        chunk_index=0,
        chunk_text="orphan by design",
        embedding=[0.0] * settings.EMBEDDING_DIMENSION,
        embedding_model="stub-embed",
        embedding_dimension=settings.EMBEDDING_DIMENSION,
    )
    document.delete()
    assert ContentChunk.objects.filter(pk=content_chunk.pk).exists()


# --- Tags and ContentTags ---------------------------------------------------------


def test_tag_name_is_normalised_on_save():
    tag = Tag.objects.create(tag_name="  Human   Resources ", dimension="Department")
    tag.refresh_from_db()
    assert tag.tag_name == "human resources"
    assert tag.active is True


def test_tag_name_is_unique_within_a_dimension_after_normalisation():
    Tag.objects.create(tag_name="Finance", dimension="Department")
    with pytest.raises(IntegrityError), transaction.atomic():
        Tag.objects.create(tag_name="  FINANCE ", dimension="Department")


def test_the_same_tag_name_may_exist_in_another_dimension():
    Tag.objects.create(tag_name="Finance", dimension="Department")
    Tag.objects.create(tag_name="Finance", dimension="Topic")
    assert Tag.objects.filter(tag_name="finance").count() == 2


def test_tag_dimension_vocabulary():
    assert choices_of(Tag, "dimension") == list(CLASSIFICATION_DIMENSIONS)
    with pytest.raises(ValidationError) as excinfo:
        Tag(tag_name="blue", dimension="Colour").full_clean()
    assert "dimension" in excinfo.value.error_dict


def test_content_tag_vocabularies_and_defaults(document):
    assert choices_of(ContentTag, "source_type") == list(SOURCE_TYPES)
    assert choices_of(ContentTag, "applied_by") == list(TAG_APPLIED_BY_VALUES)
    tag = Tag.objects.create(tag_name="leave", dimension="Topic")
    content_tag = ContentTag.objects.create(
        tag=tag, source_type=SOURCE_TYPES[0], source_id=document.id, applied_by="ai"
    )
    assert content_tag.confirmed is False
    content_tag.applied_by = "robot"
    with pytest.raises(ValidationError) as excinfo:
        content_tag.full_clean()
    assert "applied_by" in excinfo.value.error_dict


def test_a_tag_in_use_is_protected_not_deleted(document):
    tag = Tag.objects.create(tag_name="leave", dimension="Topic")
    ContentTag.objects.create(tag=tag, source_type=SOURCE_TYPES[0], source_id=document.id, applied_by="user")
    with pytest.raises(ProtectedError):
        tag.delete()
    tag.active = False  # the schema's answer: deactivate instead
    tag.save()
    assert Tag.objects.get(pk=tag.pk).active is False


# --- Departments (documents 0015, D-129) ------------------------------------------------------


def test_department_name_is_normalised_on_save_and_keeps_its_case():
    """Unlike ``Tag.save()``: the classifier writes the list's spelling into ``Documents.department``,
    and FR-14's and FR-15's filters would split by case if it were lower-cased (D-129)."""
    department = Department.objects.create(name="  Human \t  Resources ")
    department.refresh_from_db()
    assert department.name == "Human Resources"
    assert (department.active, department.grown) == (True, False)


def test_department_names_are_unique_ignoring_case_after_normalisation():
    Department.objects.create(name="Human Resources")
    with pytest.raises(IntegrityError), transaction.atomic():
        Department.objects.create(name="  HUMAN   resources ")
    assert list(Department.objects.values_list("name", flat=True)) == ["Human Resources"]
