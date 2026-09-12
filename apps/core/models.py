"""Abstract base models shared by every app.

The proposal's schema uses UUID primary keys throughout, so every concrete model
mixes in UUIDPrimaryKeyMixin. TimeStampedModel adds the created/updated pair.
"""

import uuid

from django.db import models


class UUIDPrimaryKeyMixin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
