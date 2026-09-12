"""Shared model helpers: the UUID primary key and fixed-vocabulary field builders.

docs/schema-v1.md uses UUID primary keys throughout, named per table (``user_id``,
``doc_id``, ...). ``uuid_primary_key()`` is the single definition of that key: every
schema-v1 model declares ``id = uuid_primary_key("<table>_id")`` so the column is
named as the document says while Python code keeps ``id`` and ``pk``.

``vocabulary_field()`` builds every fixed-vocabulary column from the tuples in
apps.core.constants; no model writes a vocabulary value as a literal.
"""

import uuid

from django.db import models

# Column sizing for the schema; not tuned values, so they live with the models.
NAME_MAX_LENGTH = 255  # titles, names, addresses
VOCABULARY_MAX_LENGTH = 32  # fixed-vocabulary columns; the longest value is 21 characters


def uuid_primary_key(db_column: str | None = None) -> models.UUIDField:
    """The UUID primary key every table uses, with the column named as schema v1 says."""
    return models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False, db_column=db_column
    )


def vocabulary_choices(values) -> list[tuple[str, str]]:
    return [(value, value) for value in values]


def vocabulary_field(values, **kwargs) -> models.CharField:
    """A CharField restricted to a fixed vocabulary from apps.core.constants."""
    return models.CharField(
        max_length=VOCABULARY_MAX_LENGTH, choices=vocabulary_choices(values), **kwargs
    )

