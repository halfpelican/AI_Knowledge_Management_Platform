"""The invariant-2 cascade: a source's visibility change re-stamps its chunks.

CLAUDE.md section 6 invariant 2, in full, is what this module exists to make true:

    ``visible_to_roles`` is denormalised onto ``ContentChunks``, stamped at ingestion from
    the owning Document or Meeting, so invariant 1 is a predicate on the same table as the
    vector rather than a discipline someone has to remember. No query shape can rank
    first. Changing a source's visibility **re-stamps every one of its chunks in the same
    transaction** — that cascade is a model-level guarantee, not a convention, and it has
    its own test. See D-17.

**Why this has to exist at all, and what its absence cost.** The denormalised stamp is what
makes FR-11 structural (``apps/retrieval/scoping.py`` filters on the chunk row, so no query
shape can rank before it filters), and the price of denormalisation is that the derived copy
does not move when the original does. Until this module, nothing moved it: narrowing a
Document to ``[Administrator]`` and saving removed it from ``GET /api/documents``, whose
filter is on the source row, and left ``POST /api/ask`` answering an Employee with a
citation from it, because that filter is on the chunk, which still carried both roles. One
change, two filters, two different answers — the worse of them being the one that returns
content. That was measured, not argued, at Stage 4 item 11 and recorded there as a strict
xfail; this module is what takes the marker off.

**The general shape of the bug, because this is one instance of it.** A derived record does
not carry visibility of its own and nothing re-derives it: a chunk is stamped from its
source at ingestion, and an answer is generated under the role its asker held at the time.
When the source's visibility or the reader's role changes afterwards, something has to
revisit the derived record. Here it is revisited eagerly, at the moment of the change,
because the chunk stamp is a *stored predicate* that retrieval trusts without re-deriving.
Where the derived record is a stored *answer*, the same problem is answered the other way
round — re-filtered on read, through the same ``scoped_chunks`` predicate, because a
statement's citation is checked against the reader's role at the time of reading
(``apps/api/serializers.py``, the conversation turn). Two mechanisms, one rule: nothing
downstream of a stamp may be older than the stamp.

**No vector is touched and no text is re-read.** The embedding is a function of the chunk
text, which a visibility change does not alter, so re-embedding would be pure cost and a
re-index event where none happened (risk R10's rule is about the *model* changing, not the
scope). Only the stamp moves. Widening moves it exactly as narrowing does: a document
narrowed by mistake and widened again is answerable again, with no re-ingestion.

**No database foreign key can do this.** ``ContentChunks`` references its source as
``(source_type, source_id)`` with no FK (D-07), so there is no cascade for Postgres to
perform and no ``ON UPDATE`` to declare. It is application code by construction, which is
also why it belongs on the model rather than in a view: the write and the cascade have to be
the same event.

**A ``save()`` override, not a signal.** Both would run on a save, and the choice was made
on the two properties invariant 2 names — *same transaction* and *model-level guarantee*:

- ``post_save`` runs inside whatever transaction the caller happened to open. A save in
  autocommit — which is every ``document.save()`` not already inside an ``atomic()`` block —
  commits the source row *before* the receiver runs, so "in the same transaction as the
  source's own save" is literally false and a failure in the cascade leaves the source
  narrowed and its chunks wide. The override opens the ``atomic()`` block itself, so the two
  writes commit together or neither does, whatever the caller did.
- ``pre_save`` cannot know the save succeeded, so it would re-stamp chunks for a write that
  may still fail.
- A signal receiver is only connected if its module is imported, which is an ``AppConfig``
  import away from being silently absent. A guarantee that can be disconnected by an import
  is a convention. The override is on the class that owns the column.

**``QuerySet.update()`` is covered too**, by ``VisibilityCascadeQuerySet``, because
``update()`` bypasses ``save()`` and every signal by design and is reachable: it is how
``apps/api`` already writes several single-column changes, and an FR-15 bulk visibility edit
is the obvious next caller. Two paths write the column, so both cascade.

**COVERAGE, MEASURED RATHER THAN REASONED — and corrected on 25 September 2026.** This
paragraph previously said ``bulk_update()`` and ``bulk_create()`` were not covered. That was
**wrong**, and wrong in the *safe* direction, which is worse for maintenance than being wrong
the other way round: a reader who believes ``bulk_update`` is uncovered does not write the
test for it, so the claim protects nothing and suppresses the check that would have. Measured
on **Django 5.2.17**, against the real database, every ORM write path that reaches the column:

===========================================================  ==========
write path                                                   cascades
===========================================================  ==========
``save()``                                                   yes
``save(update_fields=["visible_to_roles"])``                 yes
``save(update_fields=[...])`` not naming the column          no write, so nothing to cascade
``QuerySet.update()``                                        yes
``QuerySet.update()`` filtered on the column being written   yes
expression update (``F()``, ``Func``, ``Value``)             yes — and it stamps the value the database stored
``bulk_update()``                                            **yes, but see below**
``update_or_create()``                                       yes
``bulk_create(update_conflicts=True, update_fields=[...])``  **NO — a known hole**
raw SQL, ``psql``                                            no
===========================================================  ==========

``update_or_create`` cascades because it ends in ``save()``.

**``bulk_update()`` cascades BY ACCIDENT, not by design, and that is worth knowing rather
than relying on.** Django implements it internally as ``self.filter(pk__in=pks).update(
**kwargs)`` — so it inherits ``VisibilityCascadeQuerySet.update`` for free. The coverage is
therefore held hostage to a dependency's implementation detail: a Django release that
reimplements ``bulk_update`` as a single ``CASE WHEN`` statement would make invariant 2 false
again **with every existing test still green**, which is the same shape as the original
defect — true where it was checked and false where it was used. The test that guards it is
consequently BEHAVIOURAL (``apps/core/tests/test_visibility_cascade.py``, the write-path
matrix): it asserts the condition invariant 2 states — every chunk carries its source's
scope — over each write path in turn, so it fails on a Django upgrade rather than on a
refactor of this module.

**``bulk_create(update_conflicts=True, update_fields=["visible_to_roles"])`` is a KNOWN HOLE,
pinned by a test rather than fixed.** It is an INSERT ... ON CONFLICT DO UPDATE, which never
touches ``save()`` and is not routed through ``update()``, so an upsert writing the column
leaves the chunks carrying the old scope. Nothing in this repository upserts a source today;
FR-15's bulk visibility editing is the obvious first caller, and closing it is about six
lines in the same shape as the ``update()`` override. It is pinned instead of believed closed
because an unpinned "not covered" claim is exactly how invariant 2's own falsehood survived
thirteen days — see ``test_bulk_create_upsert_is_a_known_hole_and_does_not_cascade``.

Raw SQL and a ``psql`` session are outside the ORM entirely and no application guarantee can
reach them; ``manage.py reindex`` re-derives the stamp from the source as it rebuilds each
chunk, so it is correct by a different route. The remedy where one is ever needed is
``restamp_chunks`` below, called directly.
"""

from collections import defaultdict

from django.apps import apps as installed_apps
from django.db import models, transaction

VISIBILITY_FIELD = "visible_to_roles"


def _chunk_model():
    """``ContentChunk``, resolved at call time.

    Looked up through the app registry rather than imported at module scope so that
    ``apps.documents.models`` and ``apps.meetings.models`` can both import this module:
    ``ContentChunk`` lives in the first of those, and a module-level import here would be a
    cycle the moment ``Document`` used the mixin.
    """
    return installed_apps.get_model("documents", "ContentChunk")


def restamp_chunks(*, source_type: str, source_ids, visible_to_roles) -> int:
    """Re-stamp every chunk of these sources with this scope. Returns rows written.

    One UPDATE statement, and the ``exclude`` is what makes it cheap enough to run on every
    save that writes the column: a chunk already carrying the scope is not rewritten, so the
    ordinary case (a save that did not change the visibility, or a source with no chunks
    yet) writes nothing and needs no record of what the previous value was. That is the
    whole reason there is no change detection in this module — nothing has to remember the
    old array, compare it, or keep a shadow copy on the instance that a ``refresh_from_db``
    could invalidate. The cascade is stated as a condition to restore rather than as a diff
    to apply: **every chunk of this source carries this source's scope**, which is true
    afterwards whether or not it was true before.

    Array equality in Postgres is ordered, so ``["Employee", "Administrator"]`` and
    ``["Administrator", "Employee"]`` are different values and the second would be rewritten
    over the first. That is correct rather than merely harmless: the chunk is meant to carry
    the source's array, and ``scoped_chunks`` tests membership, so neither order changes who
    may read it.
    """
    roles = list(visible_to_roles)
    identifiers = list(source_ids)
    if not identifiers:
        return 0
    return (
        _chunk_model()
        .objects.filter(source_type=source_type, source_id__in=identifiers)
        .exclude(**{VISIBILITY_FIELD: roles})
        .update(**{VISIBILITY_FIELD: roles})
    )


class VisibilityCascadeQuerySet(models.QuerySet):
    """A queryset whose ``update()`` cascades a visibility change to the chunks.

    ``update()`` is a single SQL statement that never instantiates a model, so it runs no
    ``save()`` and sends no signal — the documented behaviour, and the reason a guarantee
    placed only on ``save()`` is one ``objects.filter(...).update(...)`` away from being
    bypassed.

    The affected primary keys are read **before** the update, because the queryset's own
    filter may be on the column being written (``filter(visible_to_roles=[...]).update(
    visible_to_roles=[...])`` matches nothing once it has run) and because a filter on
    anything else may equally stop matching. The new scope is then read back from the rows
    rather than taken from ``kwargs``, so an expression — ``F()``, ``Value()``, a
    ``Func`` appending a role — cascades the value the database actually stored instead of
    an object this method would have to interpret. Grouping by the stored array means one
    statement per distinct scope, which is one statement in every real case.
    """

    def update(self, **kwargs):
        if VISIBILITY_FIELD not in kwargs:
            return super().update(**kwargs)
        source_type = self.model.visibility_source_type
        with transaction.atomic():
            identifiers = list(self.values_list("pk", flat=True))
            updated = super().update(**kwargs)
            stored = (
                self.model._default_manager.filter(pk__in=identifiers)
                .values_list("pk", VISIBILITY_FIELD)
            )
            by_scope = defaultdict(list)
            for identifier, roles in stored:
                by_scope[tuple(roles)].append(identifier)
            for roles, identifiers_in_scope in by_scope.items():
                restamp_chunks(
                    source_type=source_type,
                    source_ids=identifiers_in_scope,
                    visible_to_roles=list(roles),
                )
            return updated


class VisibilityCascadeMixin:
    """Mixin for a source model whose ``visible_to_roles`` chunks must follow.

    A plain mixin rather than an abstract model, and a manager rather than a field: neither
    adds a column, an option or a base Django's autodetector records, so the cascade needs
    **no migration** — which matters, because it is being added to two tables that already
    have applied migrations in other environments and migrations here are additive (CLAUDE.md
    section 7).

    A model using this declares ``visibility_source_type`` (one of ``SOURCE_TYPES``) and
    sets ``objects = VisibilityCascadeQuerySet.as_manager()``. Listed before ``models.Model``
    in the bases so that this ``save`` is the one that runs.
    """

    #: The ``ContentChunks.source_type`` value this model's rows are the source of.
    visibility_source_type: str = ""

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and VISIBILITY_FIELD not in set(update_fields):
            # The save did not write the column, so the chunks are not stale with respect to
            # it, and the instance's in-memory array may itself be the stale thing —
            # ``save(update_fields=["status"])`` is how ingestion advances a document, and
            # cascading from that instance would push a possibly outdated scope onto rows
            # that were correct. The cascade mirrors what the save wrote, exactly.
            return super().save(*args, **kwargs)
        with transaction.atomic():
            # Invariant 2's "in the same transaction": the block is opened here rather than
            # relied upon from the caller, so a failure in either write rolls back both and a
            # source is never narrowed while its chunks stay wide. Nested inside a caller's
            # ``atomic()`` this is a savepoint, which composes the same way.
            super().save(*args, **kwargs)
            restamp_chunks(
                source_type=self.visibility_source_type,
                source_ids=[self.pk],
                visible_to_roles=getattr(self, VISIBILITY_FIELD),
            )
