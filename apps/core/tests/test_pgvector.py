"""Stage 1 item 3: the vector extension is enabled by migration, not by hand."""

import pytest
from django.db import connection


@pytest.mark.django_db
def test_database_is_postgresql():
    # One PostgreSQL database holds the schema and the vectors (NFR-21); a suite
    # pointed at anything else proves nothing about the real backend.
    assert connection.vendor == "postgresql"


@pytest.mark.django_db
def test_vector_extension_is_installed():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        assert cursor.fetchone() == (1,)
