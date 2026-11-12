"""``scripts/objective05_verify.py`` reports D-128's departure from Objective 05's clause 3 rather than
hiding it (D-128, 12 November 2026).

Clause 3: "suggested values falling outside the established scheme must be discarded in the
Department, Project and Process dimensions while being proposed for confirmation in the Topic
dimension only". Since D-128 the shipped build holds a Project or Process value below the threshold
and creates and links a value at or above it, so the script counts:

- a Topic entry of ``proposed_tags`` as ``topic_proposed``, which the clause asks for;
- a Project or Process entry as ``project_process_proposed``, a clause 3 violation;
- an AI link whose Tag is grown as ``created_by_classifier``, a clause 3 violation: on a measurement
  database the scheme is seeded ``--scheme-only``, never grown, and no person acts.

The script runs here as an operator runs it, through ``main()`` with its arguments, against this
test's database, on rows the apply layer itself wrote (``apply_classification``) for documents
titled as the frozen reference set titles them. The reference set and the manifest are only read.
Two things are replaced, because neither is under test and neither may run here: FLM's version (no
FLM is reached) and the commit record (no git state is asserted).
"""

import json
import sys
from pathlib import Path

import django
import pytest

from apps.core.constants import (
    EMPLOYEE_ROLE_NAME,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    TOPIC_DIMENSION,
)
from apps.documents.classification import apply_classification, confidence_threshold
from apps.documents.models import Document, Tag

from .classification_builders import EPSILON, STUB_CHAT_MODEL, classification, scheme

pytestmark = pytest.mark.django_db

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REFERENCE = REPOSITORY_ROOT / "corpus" / "objective-05" / "reference.json"
# The builders' model, which every classification here carries: its own threshold.
THRESHOLD = confidence_threshold(STUB_CHAT_MODEL)
BELOW = round(THRESHOLD - EPSILON, 3)


def reference_documents():
    """``[(id, title), ...]`` of the frozen reference set, in its order."""
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return [(entry["id"], entry["title"]) for entry in reference["documents"]]


@pytest.fixture
def titled(employee):
    """The reference set's documents, one per call, in its order: ``(id, Document)``."""
    remaining = iter(reference_documents())

    def make():
        reference_id, title = next(remaining)
        return reference_id, Document.objects.create(
            title=title, file_type="txt", uploaded_by=employee, visible_to_roles=[EMPLOYEE_ROLE_NAME]
        )

    return make


def classified(document, *tags, project=(), process=(), topic=()):
    """The apply layer's own record of a run that suggested ``tags``, against a scheme written by
    hand. The department is left blank and discarded, which clause 3 counts and does not fault."""
    apply_classification(
        document, classification(tags=tags), scheme=scheme(project=project, process=process, topic=topic)
    )


def clause_3(monkeypatch, tmp_path):
    """Run the script through ``main()`` against this test's database; returns its clause 3."""
    monkeypatch.setattr(sys, "path", list(sys.path))  # the script inserts the repository root
    from scripts import objective05_verify as script

    monkeypatch.setattr(django, "setup", lambda: None)  # pytest has set Django up already
    unknown = script.check_flm.UNKNOWN_VERSION
    monkeypatch.setattr(
        script.check_flm, "flm_version",
        lambda *args, **kwargs: script.check_flm.FlmVersion(cli=unknown, cli_output=None, server=unknown),
    )
    monkeypatch.setattr(
        script.measurement_record, "run_record",
        lambda *, dump_sha256, database, flm: {
            "commit_sha": "0" * 40, "uncommitted_tracked_changes": False, "uncommitted_tracked_files": [],
            "dump_sha256": dump_sha256, "database": database, "flm_version": flm,
        },
    )
    out = tmp_path / "verification"
    monkeypatch.setattr(
        sys, "argv", ["objective05_verify.py", "--dump-sha256", "b" * 64, "--out-dir", str(out)]
    )
    assert script.main() == 0
    return json.loads((out / "verification.json").read_text(encoding="utf-8"))["summary"]["clause_3"]


def test_a_topic_proposal_is_what_clause_3_asks_for(titled, monkeypatch, tmp_path):
    _, document = titled()
    classified(document, (TOPIC_DIMENSION, "budget planning", BELOW))

    result = clause_3(monkeypatch, tmp_path)

    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (1, 0, 0)
    assert result["violations"] == []
    assert result["passes"] is True


@pytest.mark.parametrize("dimension", [PROJECT_DIMENSION, PROCESS_DIMENSION])
def test_a_project_or_process_proposal_is_a_clause_3_violation(titled, monkeypatch, tmp_path, dimension):
    _, topic_document = titled()
    classified(topic_document, (TOPIC_DIMENSION, "budget planning", BELOW))
    reference_id, document = titled()
    classified(document, (dimension, "harbour upgrade", BELOW))

    result = clause_3(monkeypatch, tmp_path)

    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (1, 1, 0)
    [violation] = result["violations"]
    assert violation.startswith(f"{reference_id} {dimension} value 'harbour upgrade' proposed")
    assert result["passes"] is False


def test_an_ai_link_to_a_value_the_classifier_created_is_a_clause_3_violation(titled, monkeypatch, tmp_path):
    """Against a scheme seeded ``--scheme-only`` (vocabulary, not grown), an AI link to a seeded value
    is clause 3's business as usual, and one to a value the classifier created, grown, is not."""
    Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)  # seeded, not grown
    _, seeded = titled()
    classified(seeded, (PROCESS_DIMENSION, "purchasing", THRESHOLD), process=["purchasing"])
    reference_id, created = titled()
    classified(created, (PROJECT_DIMENSION, "harbour upgrade", THRESHOLD))
    assert set(Tag.objects.values_list("tag_name", "grown")) == {("purchasing", False), ("harbour upgrade", True)}

    result = clause_3(monkeypatch, tmp_path)

    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (0, 0, 1)
    [violation] = result["violations"]
    assert violation.startswith(f"{reference_id} {PROJECT_DIMENSION} value 'harbour upgrade' created")
    assert result["passes"] is False
