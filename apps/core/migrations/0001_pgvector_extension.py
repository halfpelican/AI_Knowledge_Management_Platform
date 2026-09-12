"""Enable the pgvector extension (Stage 1 item 3, CLAUDE.md section 3).

One database holds both the relational schema and the vectors, so a record and its
embedding commit in the same transaction (NFR-21). Reversible: unapplying drops
the extension.
"""

from django.db import migrations
from pgvector.django import VectorExtension


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        VectorExtension(),
    ]
