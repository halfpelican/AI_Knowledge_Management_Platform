"""``scripts/seed_objective02_tags.py`` marks grown the values only restricted material carries (D-105's
dated note of 10 November 2026, night: the security review of ``84b5771``).

In its linked mode the seed writes the manifest's links and then marks grown every seeded value with
links and no link on a source every role reads, the marking ``documents 0011`` applies to an
existing database. On the objective-02 manifest that is the Project value ``atlas``, carried only by
D09 and D15, both Administrator-only. ``--scheme-only`` links nothing and marks nothing: Objective
05's start, fourteen unlinked values, none grown.

The script is run here as an operator runs it, through ``main()`` with its arguments. The documents
it links are made from the manifest with the manifest's ``visible_to_roles``, which is what
``scripts/ingest_objective02.py`` gives them.
"""

import json
import sys

import django
import pytest

from apps.core.constants import EFFECTIVE_ROLES, ROLE_NAMES
from apps.documents.models import ContentTag, Document, Tag, normalise_tag_name

pytestmark = pytest.mark.django_db


def seed_module():
    from scripts import seed_objective02_tags

    return seed_objective02_tags


def run(monkeypatch, *arguments):
    seed = seed_module()
    monkeypatch.setattr(sys, "argv", ["seed_objective02_tags.py", *arguments])
    monkeypatch.setattr(sys, "path", list(sys.path))  # the script inserts the repository root
    monkeypatch.setattr(django, "setup", lambda: None)  # pytest has set Django up already
    assert seed.main() == 0


def manifest():
    return json.loads(seed_module().MANIFEST.read_text(encoding="utf-8"))


def readable_by_every_role(roles):
    return all(set(roles) & set(EFFECTIVE_ROLES[role_name]) for role_name in ROLE_NAMES)


def values_only_restricted_material_carries(items):
    """From the manifest itself: the values no document every role reads carries."""
    carried, readable = set(), set()
    for item in items:
        for dimension, values in (item.get("tags") or {}).items():
            for value in values:
                key = (dimension, normalise_tag_name(value))
                carried.add(key)
                if readable_by_every_role(item["visible_to_roles"]):
                    readable.add(key)
    return carried - readable


@pytest.fixture
def corpus(employee):
    """The manifest's tagged documents, each with the manifest's visible_to_roles."""
    items = [item for item in manifest()["items"] if item.get("tags")]
    for item in items:
        Document.objects.create(
            title=item["title"], file_type="txt", uploaded_by=employee,
            visible_to_roles=item["visible_to_roles"],
        )
    return items


def test_the_linked_mode_marks_grown_the_values_only_restricted_material_carries(corpus, monkeypatch):
    run(monkeypatch)

    assert ContentTag.objects.exists()
    grown = set(Tag.objects.filter(grown=True).values_list("dimension", "tag_name"))
    assert grown == values_only_restricted_material_carries(corpus)
    assert grown == {("Project", "atlas")}  # D09 and D15, both Administrator-only
    # A value that restricted material also carries stays vocabulary (the review's finding 1's).
    for name in ("purchasing", "onboarding", "finance", "people"):
        assert Tag.objects.get(tag_name=name).grown is False


def test_the_scheme_only_mode_marks_nothing(monkeypatch):
    run(monkeypatch, "--scheme-only")

    assert not ContentTag.objects.exists()
    assert Tag.objects.count() == 14
    assert not Tag.objects.filter(grown=True).exists()
