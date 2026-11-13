"""``scripts/objective05_verify.py`` scores Objective 05's clause 3 as written, and reports a departure
from it rather than hiding it.

Clause 3: "suggested values falling outside the established scheme must be discarded in the
Department, Project and Process dimensions while being proposed for confirmation in the Topic
dimension only". The shipped build meets it again since D-129 (13 November 2026), which reverses
D-128's creation of values: a classification proposes a Topic outside the scheme and discards a
Project or Process value. From 12 to 13 November 2026, D-128 held a Project or Process value below
the threshold and created and linked a value at or above it. The script still counts such a
departure strictly:

- a Topic entry of ``proposed_tags`` as ``topic_proposed``, which the clause asks for;
- a Project or Process entry as ``project_process_proposed``, a clause 3 violation;
- an AI link whose Tag is grown as ``created_by_classifier``, a clause 3 violation: on a measurement
  database the scheme is seeded ``--scheme-only``, never grown, and no person acts.

The script runs here as an operator runs it, through ``main()`` with its arguments, against this
test's database, for documents titled as the frozen reference set titles them, on rows the apply
layer itself wrote (``apply_classification``). The departures D-128 produced are written onto
those rows directly, since the shipped build no longer produces them. The reference set and the
manifest are only read.
Two things are replaced, because neither is under test and neither may run here: FLM's version (no
FLM is reached) and the commit record (no git state is asserted).
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

import django
import pytest

from apps.core.constants import (
    AI_APPLIED,
    EMPLOYEE_ROLE_NAME,
    PROCESS_DIMENSION,
    PROJECT_DIMENSION,
    SOURCE_TYPES,
    TOPIC_DIMENSION,
)
from apps.documents.classification import apply_classification, confidence_threshold
from apps.documents.models import ContentTag, Document, DocumentAnalysis, Tag

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
@pytest.mark.parametrize("confidence", [BELOW, THRESHOLD], ids=["below", "at"])
def test_a_project_or_process_value_outside_the_scheme_is_discarded_and_meets_clause_3(
    titled, monkeypatch, tmp_path, dimension, confidence
):
    """The shipped build since D-129: discarded at any confidence, nothing proposed or created."""
    _, document = titled()
    classified(document, (dimension, "harbour upgrade", confidence))

    result = clause_3(monkeypatch, tmp_path)

    assert result["project_process_discarded"] == 1
    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (0, 0, 0)
    assert result["violations"] == []
    assert result["passes"] is True


@pytest.mark.parametrize("dimension", [PROJECT_DIMENSION, PROCESS_DIMENSION])
def test_a_project_or_process_proposal_is_a_clause_3_violation(titled, monkeypatch, tmp_path, dimension):
    """A Project or Process proposal as D-128 made one, written onto the row."""
    _, topic_document = titled()
    classified(topic_document, (TOPIC_DIMENSION, "budget planning", BELOW))
    reference_id, document = titled()
    classified(document)
    analysis = DocumentAnalysis.objects.get(document=document)
    analysis.proposed_tags = [{"dimension": dimension, "value": "harbour upgrade", "confidence": BELOW}]
    analysis.save(update_fields=["proposed_tags"])

    result = clause_3(monkeypatch, tmp_path)

    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (1, 1, 0)
    [violation] = result["violations"]
    assert violation.startswith(f"{reference_id} {dimension} value 'harbour upgrade' proposed")
    assert result["passes"] is False


def test_an_ai_link_to_a_value_the_classifier_created_is_a_clause_3_violation(titled, monkeypatch, tmp_path):
    """Against a scheme seeded ``--scheme-only`` (vocabulary, not grown), an AI link to a seeded value
    is clause 3's business as usual, and one to a value the classifier created, grown, is not. The
    created value is written onto the rows as D-128 made one; the shipped build makes none."""
    Tag.objects.create(tag_name="purchasing", dimension=PROCESS_DIMENSION)  # seeded, not grown
    _, seeded = titled()
    classified(seeded, (PROCESS_DIMENSION, "purchasing", THRESHOLD), process=["purchasing"])
    reference_id, created = titled()
    classified(created)
    ContentTag.objects.create(
        tag=Tag.objects.create(tag_name="harbour upgrade", dimension=PROJECT_DIMENSION, grown=True),
        source_type=SOURCE_TYPES[0], source_id=created.pk, applied_by=AI_APPLIED, confirmed=False,
        provisional=False, confidence=Decimal(str(THRESHOLD)),
    )
    assert set(Tag.objects.values_list("tag_name", "grown")) == {("purchasing", False), ("harbour upgrade", True)}

    result = clause_3(monkeypatch, tmp_path)

    assert (result["topic_proposed"], result["project_process_proposed"], result["created_by_classifier"]) == (0, 0, 1)
    [violation] = result["violations"]
    assert violation.startswith(f"{reference_id} {PROJECT_DIMENSION} value 'harbour upgrade' created")
    assert result["passes"] is False
