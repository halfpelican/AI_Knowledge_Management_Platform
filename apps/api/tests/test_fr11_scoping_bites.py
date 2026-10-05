"""Do the FR-11 assertions detect the bug they exist to detect? The vacuity guard.

``test_fr11_scoping.py`` is the evidence file for the invariant this project cannot get
wrong, and the failure mode of an evidence file is that it passes for the wrong reason. An
absence is trivially satisfiable: if ``assert_nothing_restricted_reached`` were looking at
the wrong field, or comparing empty sets, or reading a body that never contained the
material for an unrelated reason, every test over there would be green and would mean
nothing. Nothing in that file can establish that it would go red.

So the bug is installed here and the assertions are expected to fail.

``leaky`` replaces the pipeline's ``candidate_chunks`` with one that drops the FR-11 role
predicate and keeps everything else — comparable embedding model, ranking, threshold,
truncation, generation, verification. That is precisely the **post-filter shape** invariant
1 forbids: a ranked list that includes material the asking role may not see. No production
code is modified; the substitution lives and dies inside the test.

What each test below asserts is therefore the contrapositive of FR-11: **with the predicate
gone, the evidence file fails.** If one of these ever passes-by-not-failing, the
corresponding assertion over there has become decoration and the real run is not evidence of
anything. This file is short on purpose: it guards the four absences and the two properties
that carry the requirement, not every test in the suite.
"""

import pytest

import apps.retrieval.pipeline as pipeline
from apps.api.tests import test_fr11_scoping as fr11
from apps.documents.models import ContentChunk

pytestmark = pytest.mark.django_db


@pytest.fixture
def service(monkeypatch):
    return fr11.install(monkeypatch, fr11.ControlledService())


@pytest.fixture
def overlapping_corpus(employee, administrator):
    return fr11.build_corpus(employee, administrator, shared_cosine=fr11.ABOVE)


@pytest.fixture
def only_restricted_answers(employee, administrator):
    return fr11.build_corpus(employee, administrator, shared_cosine=fr11.BELOW)


@pytest.fixture
def leaky(monkeypatch):
    """The candidate set with FR-11's predicate removed: everything comparable, then ranked.

    The embedding-model predicate stays, because dropping both would test two things at once
    and the risk R10 filter has its own tests. This is the one-line version of the mistake
    the invariant is written against.
    """

    def unscoped(*, role_name, embedding_model):
        return ContentChunk.objects.filter(embedding_model=embedding_model)

    monkeypatch.setattr(pipeline, "candidate_chunks", unscoped)


def test_the_four_absences_fail_when_the_role_predicate_is_dropped(
    employee_client, service, overlapping_corpus, leaky
):
    """The whole helper, as one assertion: it raises against a leaking pipeline."""
    response = fr11.ask(employee_client)

    assert response.status_code == 200
    with pytest.raises(AssertionError):
        fr11.assert_nothing_restricted_reached(response, service, overlapping_corpus)


def test_the_payload_assertion_alone_fails_when_the_role_predicate_is_dropped(
    employee_client, service, overlapping_corpus, leaky
):
    """Assertion 4 on its own, spelled out rather than taken on the helper's word: with the
    predicate gone, the restricted passage really is in what ``generate_statements`` was
    handed. That is what the evidence file asserts the absence of."""
    fr11.ask(employee_client)

    [(prompted_question, passages)] = service.generate_calls
    assert str(overlapping_corpus.restricted_document_chunk.id) in {
        passage.chunk_id for passage in passages
    }
    from apps.ai.prompting import build_user_prompt

    assert fr11.RESTRICTED_DOCUMENT_TEXT in build_user_prompt(prompted_question, passages)


def test_the_headline_no_answer_becomes_an_answer_when_the_role_predicate_is_dropped(
    employee_client, service, only_restricted_answers, leaky
):
    """The headline test's premise, inverted: the Employee is answered from the document
    their role cannot see, and the count rises to include it. The no-answer over there is
    therefore the filter's doing and not a thin corpus."""
    body = fr11.ask(employee_client).json()

    assert body["answered"] is True
    assert body["result_count"] == 2  # the two Administrator-only chunks above the floor
    # Answered FROM the restricted material: every cited chunk is one the Employee may not see.
    cited = {statement["chunk_id"] for statement in body["statements"]}
    assert cited and cited <= only_restricted_answers.restricted_chunk_ids
    # The title is the one thing that no longer leaks, and that is D-53 rather than FR-11's
    # chunk predicate. Since Stage 5 item 1 the Sources panel reads source rows through
    # ``scoped_documents``, which tests the source's own row, so a leaking candidate set loses
    # the title at that second layer. Until item 1 this line asserted the title WAS there.
    assert fr11.RESTRICTED_DOCUMENT_TITLE not in {source["title"] for source in body["sources"]}


def test_the_byte_identical_property_fails_when_the_role_predicate_is_dropped(
    employee_client, service, employee, administrator, leaky
):
    """"The reply does not differ whether the restricted material exists" is a real
    property, not an accident of a reply too empty to differ: with the predicate gone the
    two bodies differ."""
    corpus = fr11.build_corpus(employee, administrator, shared_cosine=fr11.ABOVE)

    with_restricted = fr11.ask(employee_client)
    corpus.delete_restricted()
    without_restricted = fr11.ask(employee_client)

    assert with_restricted.content != without_restricted.content
