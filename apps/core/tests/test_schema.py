"""Migration v1 matches docs/schema-v1.md section 1, table by table, column by column.

The expected names are transcribed from the document, not derived from the models,
so this is a check of the migrations against the document rather than of the
models against themselves.
"""

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection

pytestmark = pytest.mark.django_db

# table -> (primary-key column(s) in order, exact column set), from schema-v1.md section 1
SCHEMA_V1 = {
    "users": (
        ("user_id",),
        {"user_id", "name", "email", "password_hash", "role_id", "created_at",
         "failed_attempts", "locked_until", "last_login_at"},
    ),
    "roles": (("role_id",), {"role_id", "role_name", "description"}),
    "permissions": (("permission_id",), {"permission_id", "permission_name"}),
    "role_permissions": (("role_id", "permission_id"), {"role_id", "permission_id"}),
    "documents": (
        ("doc_id",),
        {"doc_id", "title", "file_type", "uploaded_by", "status", "uploaded_at",
         "department", "visible_to_roles"},
    ),
    "extracted_content": (
        ("content_id",),
        {"content_id", "doc_id", "extracted_text", "extracted_at"},
    ),
    "content_chunks": (
        ("chunk_id",),
        {"chunk_id", "source_type", "source_id", "chunk_index", "chunk_text", "embedding",
         "embedding_model", "embedding_dimension", "created_at"},
    ),
    "meetings": (
        ("meeting_id",),
        {"meeting_id", "title", "meeting_date", "transcript_text", "status", "created_at"},
    ),
    "meeting_attendees": (("attendee_id",), {"attendee_id", "meeting_id", "user_id"}),
    "conversations": (
        ("conversation_id",),
        {"conversation_id", "user_id", "title", "last_updated_at"},
    ),
    "query_log": (
        ("query_id",),
        {"query_id", "user_id", "conversation_id", "question", "answer_text",
         "retrieved_chunk_ids", "answered", "no_answer_reason", "answered_at"},
    ),
    "search_logs": (
        ("search_id",),
        {"search_id", "user_id", "query_text", "result_count", "searched_at"},
    ),
    "answer_citations": (
        ("citation_id",),
        {"citation_id", "query_id", "chunk_id", "statement_text", "position"},
    ),
    "tags": (("tag_id",), {"tag_id", "tag_name", "dimension", "active"}),
    "content_tags": (
        ("content_tag_id",),
        {"content_tag_id", "tag_id", "source_type", "source_id", "applied_by", "confirmed"},
    ),
}

# schema-v1.md section 2: deferred to NIT3004, must not exist in v1
SECTION_2_TABLES = {"login_attempts", "document_analysis", "mfa_recovery_codes", "knowledge_gaps"}
SECTION_2_USER_COLUMNS = {"mfa_enabled", "mfa_secret"}

OUR_APPS = ("core", "accounts", "documents", "meetings", "retrieval")


def columns_of(table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            [table],
        )
        return {row[0] for row in cursor.fetchall()}


def primary_key_of(table):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON kcu.constraint_name = tc.constraint_name
             AND kcu.table_schema = tc.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """,
            [table],
        )
        return tuple(row[0] for row in cursor.fetchall())


def public_tables():
    with connection.cursor() as cursor:
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.parametrize("table", sorted(SCHEMA_V1))
def test_table_has_exactly_the_section_1_columns(table):
    _, expected_columns = SCHEMA_V1[table]
    assert columns_of(table) == expected_columns


@pytest.mark.parametrize("table", sorted(SCHEMA_V1))
def test_table_primary_key_is_the_section_1_one(table):
    expected_primary_key, _ = SCHEMA_V1[table]
    assert primary_key_of(table) == expected_primary_key


def test_our_models_map_onto_exactly_the_section_1_tables():
    tables = {
        model._meta.db_table
        for app_label in OUR_APPS
        for model in django_apps.get_app_config(app_label).get_models()
    }
    assert tables == set(SCHEMA_V1)


def test_embedding_column_is_a_vector_sized_from_settings():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
            "WHERE a.attrelid = 'content_chunks'::regclass AND a.attname = 'embedding'"
        )
        (type_name,) = cursor.fetchone()
    assert type_name == f"vector({settings.EMBEDDING_DIMENSION})"


def test_content_chunks_has_the_two_section_1_indexes():
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'content_chunks'")
        indexes = dict(cursor.fetchall())
    assert "(source_type, source_id)" in indexes["content_chunks_source_idx"]
    assert "(embedding_model)" in indexes["content_chunks_model_idx"]


def test_section_2_tables_do_not_exist():
    assert public_tables().isdisjoint(SECTION_2_TABLES)


def test_users_has_no_section_2_or_django_default_columns():
    assert columns_of("users").isdisjoint(
        SECTION_2_USER_COLUMNS | {"is_active", "username", "is_staff", "is_superuser"}
    )


def test_django_session_table_exists():
    # D-10: sessions are Django's own framework, not a table of ours.
    assert "django_session" in public_tables()
