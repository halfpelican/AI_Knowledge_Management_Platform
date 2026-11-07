"""FR-12 steps 3 and 4: cosine ranking in application code, then TOP_K, then the floor.

The input is whatever ``scoping.candidate_chunks`` returned and nothing else. Both
FR-11 predicates — the role scope and the embedding-model match — are already
conditions on that query, so no row this module scores was ever outside the asking
role's scope, and nothing here re-checks visibility or widens the set. A passage that
reaches ``rank`` is a passage the user may read (CLAUDE.md section 6 invariant 1).

**A contradiction in the proposal, and which clause governs.** The two statements
below are about the same step and cannot both be followed:

- FR-12's Business logic (ranking) says similarity "is computed within the
  application over the stored vectors, which is adequate at the corpus scale of this
  project and keeps the retrieval mechanism transparent."
- The section 7.10 pseudocode comment at step 4 says the opposite: "Ranking is
  performed by the vector store, which holds the index built for the purpose. Reading
  every stored vector into the application and comparing them there would return the
  same passages while scanning the entire corpus for each question, and would not
  remain workable as the knowledge base grows."

**The requirement text governs**, and CLAUDE.md section 3 says the same, so ranking is
application code: ``cosine_similarity`` below, over vectors read out of the candidate
set. The pseudocode is not being overruled on the facts, only on precedence — its
objection is **correct**. This is a full scan of the candidate set on every question,
the cost grows linearly with the corpus, and an index the database already holds is
being ignored. At a 6-chunk corpus (D-37) that is measured in microseconds, so it is
an accepted limitation rather than an oversight, and it is recorded here rather than
discovered later. pgvector is installed and ``ContentChunk.embedding`` is a real
vector column sized from settings (D-03, D-08), so moving ranking into the database is
a change of this one function — an ``order_by`` on a distance expression against the
same queryset — and not a re-architecture. What must not change with it is the order
of the two filters: the scope stays in the query.

**TOP_K does not currently bind.** The corpus is 6 chunks, so after the role and
embedding-model predicates there are never 25 candidates, and ``RELEVANCE_THRESHOLD``
is doing all of the selection (D-37's erratum: "TOP_K = 25 binds even less at 6 than
at 9"). That is a property of this corpus, not of this code. The cap is implemented
and tested for the case that does not yet occur, because the first corpus large enough
to reach 25 candidates will not announce itself.

**The threshold is not applied in ``rank``.** It lives in ``admit`` so that the
pre-threshold ranked list, and in particular its top score, stays observable: that
score is what ``scripts/citation_harness.py --scores-only`` measures and what D-37 and
D-38 were decided on. Folding the floor into the ranking step would delete the only
number that says whether the threshold is set anywhere near the right place.

Not here, deliberately: the two no-answer paths and their reason codes (item 4 — this
module returns an empty list and draws no conclusion from it), generation, citation
verification and query logging.

``truncate_to_context`` joined ``rank`` and ``admit`` here at item 5 rather than taking a
module of its own: the three are one sequence of operations over one list — order it,
apply the floor, fit the budget — they share ``RankedPassage``, and each of their
docstrings refers to the other two. A module holding the third alone would have to
restate that context to be readable.
"""

from dataclasses import dataclass
from math import sqrt
from typing import Iterable
from uuid import UUID

from apps.core.constants import MAXIMUM_CONTEXT_TOKENS, RELEVANCE_THRESHOLD, TOP_K
from apps.documents.models import ContentChunk
from apps.ingestion.chunking import length_in_tokens


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Cosine similarity of two vectors, in application code.

    Lifted unchanged from ``scripts/citation_harness.py``, which measured the D-37 and
    D-38 distributions with it: if the two ever diverge, the baseline numbers stop
    describing what retrieval does.

    Both guards are load-bearing. A dimension mismatch raises rather than scoring,
    because two widths that do not match are two different embedding models and a
    number computed across them is the silent corruption of risk R10 wearing a
    plausible face; ``scoping.candidate_chunks`` and ``query_embedding`` between them
    should make it unreachable, which is why it is an exception and not a return
    value. A zero-norm vector scores 0.0 rather than dividing by zero, since a vector
    with no direction has no angle to any other one.
    """
    if len(left) != len(right):
        raise ValueError(f"dimension mismatch: {len(left)} vs {len(right)}")
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sqrt(sum(a * a for a in left))
    right_norm = sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


@dataclass(frozen=True)
class RankedPassage:
    """One scored passage: the identifier, the text, the score and where it came from.

    Frozen because nothing downstream has any business editing a score or, worse, an
    identifier: ``chunk_id`` is what citation verification checks statements against by
    set membership (invariant 5), and a mutable identifier would make that check a
    check of whatever the last caller left behind.

    ``chunk_id`` is a string because that is the form the generation prompt labels
    passages with and the form the model hands identifiers back in, so verification
    compares strings to strings and never a string to a UUID that merely looks like it.
    ``source_type`` and ``source_id`` are carried because the Sources panel will resolve
    the owning Document or Meeting from them; reading them off the row already in hand
    costs nothing, where fetching them later would be a second query over rows already
    read. The embedding is deliberately NOT carried: it has done its work by the time a
    passage is ranked, it is the largest field on the row, and the one place it could
    still go wrong is being copied somewhere it might be logged.
    """

    chunk_id: str
    chunk_text: str
    score: float
    source_type: str
    source_id: UUID


def rank(candidates: Iterable[ContentChunk], query_vector: list[float]) -> list[RankedPassage]:
    """Score every candidate, order best first, then keep at most TOP_K.

    THE ORDER OF THOSE THREE STEPS IS THE WHOLE FUNCTION. Every candidate is scored,
    the full list is sorted by score descending, and only then is it cut to TOP_K.
    Capping before sorting — slicing the candidate set and ranking the slice — would
    take 25 arbitrary rows in whatever order the database happened to return them and
    present them as the nearest 25, which is wrong in a way no output inspection would
    catch: the list comes back plausibly ordered and silently missing the best
    passages. ``apps/retrieval/tests/test_ranking.py`` pins it with rows whose database
    order is the reverse of their score order.

    ``list.sort`` is stable, so passages with equal scores keep the candidate set's own
    order rather than being shuffled. That makes a tie deterministic for a given
    queryset; it does not make it meaningful, and nothing should read significance into
    which of two equally scored passages came first.

    The threshold is NOT applied here — see the module docstring. Callers pass this
    list to ``admit`` and may read its top score first.
    """
    scored = [
        RankedPassage(
            chunk_id=str(chunk.id),
            chunk_text=chunk.chunk_text,
            # list() because pgvector hands the column back as a numpy array, and
            # cosine_similarity is written against sequences of plain floats.
            score=cosine_similarity(query_vector, list(chunk.embedding)),
            source_type=chunk.source_type,
            source_id=chunk.source_id,
        )
        for chunk in candidates
    ]
    # Sort first, cap second. Never the other way round.
    scored.sort(key=lambda passage: passage.score, reverse=True)
    return scored[:TOP_K]


def admit(ranked: list[RankedPassage]) -> list[RankedPassage]:
    """Drop every passage scoring below RELEVANCE_THRESHOLD, keeping the order.

    The comparison is ``>=``, matching proposal 7.10 line 61 exactly: a passage sitting
    precisely on the floor is admitted. FR-12 gives the reason for having a floor at
    all — results below it are "excluded rather than returned as weak matches, since a
    low-relevance result presented as an answer is worse than none". Exclusion here is
    the same shape as exclusion in ``scoping``: the passage is absent, not flagged,
    not greyed out and not counted.

    An empty return is an ordinary outcome and not an error. What the pipeline does
    with it — the no-answer response, generation never called, and the
    ``no_relevant_passage`` reason code that distinguishes this path from
    ``no_statement_verified`` (invariant 7) — is item 4's decision, not this
    function's. The value was settled on measured evidence in D-37 and re-measured in
    D-38, and was re-tuned in step 7 phase 2b on the Objective 02 development set
    (``apps/core/constants.py`` has the rule and the scores). It is not tuned here.
    """
    return [passage for passage in ranked if passage.score >= RELEVANCE_THRESHOLD]


def truncate_to_context(passages: list[RankedPassage]) -> list[RankedPassage]:
    """Fit the grounding context into MAXIMUM_CONTEXT_TOKENS, dropping the worst first.

    Proposal 7.10 lines 92-111 (FR-12 step 7). Passages are consumed in rank order, and
    when the next one will not fit the remaining budget the loop STOPS rather than
    skipping it to try the one after. The pseudocode gives the reason and it is worth
    restating: continuing would admit a weaker passage while excluding a stronger one
    purely on length. A ranking that can be re-ordered by passage size is not a ranking.

    TOP_K bounds how many passages are retrieved and this bounds how many fit in one
    generation call. They are not the same limit and the smaller of them governs.

    **The single best passage is always sent, even when it alone exceeds the budget.**
    The ``if kept and ...`` guard is what does it, and it is deliberate: dropping it
    would return the no-answer response while holding the most relevant material the
    corpus has, which reads to the user as "we know nothing about this" when the truth is
    "we found it and would not show you". An over-length prompt is the provider's to
    refuse — and a refusal is a failed attempt, retried, then an honest 503 — whereas a
    silent no-answer is not visible to anyone. This matches what the harness did when
    docs/flm-baseline.md was measured.

    Tokens are counted with ``length_in_tokens``, the project's single definition of a
    token: a whitespace-delimited word (D-31). Not a model tokeniser, so this is an
    approximation that undercounts real subword tokens by roughly 1.3x; the budget is set
    with that headroom in mind.

    MAXIMUM_CONTEXT_TOKENS is marked PROVISIONAL in apps/core/constants.py and item 5
    does NOT tune it. 4000 is the value docs/flm-baseline.md was measured at, and the
    corpus is 6 chunks of roughly 400 tokens, so the budget never binds: fitting a
    constant to a corpus that cannot exercise it would be fitting it to nothing. Same
    reasoning as TOP_K in item 3, and the same consequence — the code is written and
    tested for the case that does not yet occur.
    """
    kept: list[RankedPassage] = []
    used = 0
    for passage in passages:  # already ordered best first
        cost = length_in_tokens(passage.chunk_text)
        if kept and used + cost > MAXIMUM_CONTEXT_TOKENS:
            # The window is full. Everything remaining scores lower than everything
            # already kept, so the list is abandoned here rather than searched for a
            # shorter passage that would fit.
            break
        kept.append(passage)
        used += cost
    return kept
