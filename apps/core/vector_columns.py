"""The width a pgvector column was built with, read from the database (D-117, D-131).

Read from Postgres, not from settings or the model, because the difference between them is the
point. The model reads ``settings.EMBEDDING_DIMENSION``, while a database keeps the width its first
``migrate`` gave each column: a database keeps the provider it was set up with (D-131). pgvector
stores a ``vector(n)`` column's n as its type modifier, and an unsized column has -1.

``reindex`` refuses a chunk column of another width, and the startup check ``check_database_provider``
(``apps/ai/checks.py``) refuses either vector column of another width.
"""

from django.db import connection


class NoSuchColumn(LookupError):
    """The table or the column is not there yet: the migration that creates it has not run."""


def stored_width(model, field_name: str = "embedding") -> int | None:
    """``model``'s vector column width in the connected database, or None for an unsized column.

    Raises NoSuchColumn when the table or the column does not exist. ``to_regclass`` gives NULL for
    a table that is not there, so that case matches no row rather than raising a database error.
    """
    table = model._meta.db_table
    column = model._meta.get_field(field_name).column
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.atttypmod FROM pg_attribute a "
            "WHERE a.attrelid = to_regclass(%s) AND a.attname = %s AND NOT a.attisdropped",
            [table, column],
        )
        row = cursor.fetchone()
    if row is None:
        raise NoSuchColumn(f"{table}.{column}")
    (modifier,) = row
    return modifier if modifier > 0 else None


def describe_width(width: int | None) -> str:
    """How Postgres names the column's type: ``vector(1024)``, or ``vector`` when it is unsized."""
    return "vector" if width is None else f"vector({width})"
