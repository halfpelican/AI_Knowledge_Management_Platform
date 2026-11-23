"""Verify the PlantUML schema diagrams directly against Django's migrations.

This script builds the authoritative database schema from ``apps/*/migrations``
via Django's ``MigrationLoader`` (no live PostgreSQL server required), cross-checks
it against the current Django models, and verifies:

1. The single combined diagram (``docs/schema-diagram/kmp-schema-v2.puml``).
2. The four area-split diagrams (``docs/schema-diagram/kmp-schema-v2-*.puml``),
   treated as a disjoint partition of the 23 tables and 28 foreign keys.
3. The exact delta between the 5 November 2026 submission (15 tables, 14 FKs)
   and the current migrations (23 tables, 28 FKs).

Run from the repository root::

    python scripts/verify_schema_diagram.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps as django_apps  # noqa: E402
from django.db import models  # noqa: E402
from django.db.migrations.loader import MigrationLoader  # noqa: E402
from django.db.models.functions import Lower  # noqa: E402

OUR_APPS = ("core", "accounts", "documents", "meetings", "retrieval")

# Exact 5 November 2026 submission baseline (Capstone diary Appendix B/C, Listing 1).
NOV5_TABLES: dict[str, set[str]] = {
    "users": {
        "user_id", "name", "email", "password_hash", "role_id",
        "last_login_at", "created_at", "failed_attempts", "locked_until",
    },
    "roles": {"role_id", "role_name", "description"},
    "role_permissions": {"role_id", "permission_id"},
    "permissions": {"permission_id", "permission_name"},
    "documents": {
        "doc_id", "title", "file_type", "file_path", "content_hash",
        "file_size_bytes", "uploaded_by", "status", "uploaded_at",
        "department", "visible_to_roles",
    },
    "extracted_content": {"content_id", "doc_id", "extracted_text", "extracted_at"},
    "meetings": {
        "meeting_id", "title", "meeting_date", "transcript_text",
        "status", "created_at", "visible_to_roles",
    },
    "meeting_attendees": {"attendee_id", "meeting_id", "user_id"},
    "content_chunks": {
        "chunk_id", "source_type", "source_id", "chunk_index", "chunk_text",
        "embedding", "embedding_model", "embedding_dimension", "created_at",
        "visible_to_roles",
    },
    "tags": {"tag_id", "tag_name", "dimension", "active"},
    "content_tags": {
        "content_tag_id", "tag_id", "source_type", "source_id",
        "applied_by", "confirmed",
    },
    "conversations": {"conversation_id", "user_id", "title", "last_updated_at"},
    "query_log": {
        "query_id", "user_id", "conversation_id", "question", "answer_text",
        "retrieved_chunk_ids", "answered", "no_answer_reason", "rejected_count",
        "answered_at",
    },
    "answer_citations": {
        "citation_id", "query_id", "chunk_id", "chunk_uuid",
        "statement_text", "position",
    },
    "search_logs": {"search_id", "user_id", "query_text", "result_count", "searched_at"},
}

EXPECTED_POLYMORPHIC_LINKS: set[tuple[str, str]] = {
    ("documents", "content_chunks"),
    ("meetings", "content_chunks"),
    ("documents", "content_tags"),
    ("meetings", "content_tags"),
}

DIAGRAM_DIR = REPO_ROOT / "docs" / "schema-diagram"
COMBINED_DIAGRAM = DIAGRAM_DIR / "kmp-schema-v2.puml"
AREA_DIAGRAMS = [
    DIAGRAM_DIR / "kmp-schema-v2-accounts.puml",
    DIAGRAM_DIR / "kmp-schema-v2-documents.puml",
    DIAGRAM_DIR / "kmp-schema-v2-meetings.puml",
    DIAGRAM_DIR / "kmp-schema-v2-retrieval.puml",
]


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    not_null: bool
    puml_type: str
    is_pk: bool
    is_fk: bool
    is_unique: bool


@dataclass(frozen=True)
class ForeignKeySpec:
    child_table: str
    column: str
    parent_table: str
    nullable: bool
    one_to_one: bool
    on_delete: str


@dataclass
class TableSpec:
    app_label: str
    name: str
    pk_columns: tuple[str, ...]
    columns: dict[str, ColumnSpec]


@dataclass
class ParsedColumn:
    name: str
    required: bool
    puml_type: str
    tags: set[str]


@dataclass
class ParsedEntity:
    name: str
    alias: str
    stereotypes: set[str]
    columns: dict[str, ParsedColumn] = field(default_factory=dict)
    source_file: str = ""


@dataclass(frozen=True)
class ParsedEdge:
    left: str
    left_card: str
    dashed: bool
    right_card: str
    right: str
    label: str | None
    source_file: str


def django_field_to_puml_type(field_obj: models.Field) -> str:
    """Map a Django migration field to the PlantUML type label used in Listing 1."""
    if isinstance(field_obj, (models.ForeignKey, models.OneToOneField)):
        # All primary keys in this schema are UUIDs (docs/schema-v1.md).
        return "uuid"
    cls = type(field_obj).__name__
    if cls == "UUIDField":
        return "uuid"
    if cls in ("CharField", "EmailField", "FileField"):
        return "varchar"
    if cls == "TextField":
        return "text"
    if cls in ("IntegerField", "PositiveIntegerField"):
        return "int"
    if cls in ("BigIntegerField", "PositiveBigIntegerField"):
        return "bigint"
    if cls == "BooleanField":
        return "bool"
    if cls == "DateField":
        return "date"
    if cls == "DateTimeField":
        return "timestamp"
    if cls == "DecimalField":
        return f"decimal({field_obj.max_digits},{field_obj.decimal_places})"
    if cls == "JSONField":
        return "jsonb"
    if cls == "VectorField":
        return "vector(dim)"
    if cls == "ArrayField":
        base = django_field_to_puml_type(field_obj.base_field)
        # Listing 1 writes text[] for ArrayField(CharField) and uuid[] for ArrayField(UUIDField).
        if base == "varchar":
            return "text[]"
        return f"{base}[]"
    raise ValueError(f"Unmapped Django field type: {cls}")


def extract_migration_schema() -> tuple[dict[str, TableSpec], list[ForeignKeySpec]]:
    """Build the full schema directly from apps/*/migrations via MigrationLoader."""
    loader = MigrationLoader(None, load=True)
    state = loader.project_state()

    tables: dict[str, TableSpec] = {}
    fks: list[ForeignKeySpec] = []

    for (app_label, model_name), mstate in sorted(state.models.items()):
        if app_label not in OUR_APPS:
            continue
        table_name = mstate.options["db_table"]

        # Detect single-column unique constraints (including Lower("name") on departments).
        unique_cols: set[str] = set()
        for constraint in mstate.options.get("constraints", []):
            if isinstance(constraint, models.UniqueConstraint):
                if len(constraint.fields) == 1:
                    unique_cols.add(constraint.fields[0])
                elif len(constraint.expressions) == 1:
                    expr = constraint.expressions[0]
                    if isinstance(expr, Lower) and hasattr(expr, "source_expressions"):
                        src = expr.source_expressions[0]
                        if hasattr(src, "name"):
                            unique_cols.add(src.name)

        composite_pk: tuple[str, ...] = ()
        for field_name, field_obj in mstate.fields.items():
            if isinstance(field_obj, models.CompositePrimaryKey):
                composite_pk = tuple(field_obj.field_names)

        columns: dict[str, ColumnSpec] = {}
        pk_cols: list[str] = []

        for field_name, field_obj in mstate.fields.items():
            if isinstance(field_obj, (models.ManyToManyField, models.CompositePrimaryKey)):
                continue

            is_fk = isinstance(field_obj, (models.ForeignKey, models.OneToOneField))
            is_o2o = isinstance(field_obj, models.OneToOneField)
            col_name = field_obj.db_column or (f"{field_name}_id" if is_fk else field_name)
            is_pk = bool(field_obj.primary_key or col_name in composite_pk)
            if field_obj.primary_key:
                pk_cols.append(col_name)

            is_unique = bool(
                (getattr(field_obj, "unique", False) and not field_obj.primary_key)
                or is_o2o
                or field_name in unique_cols
                or col_name in unique_cols
            )

            columns[col_name] = ColumnSpec(
                name=col_name,
                not_null=not field_obj.null,
                puml_type=django_field_to_puml_type(field_obj),
                is_pk=is_pk,
                is_fk=is_fk,
                is_unique=is_unique,
            )

            if is_fk:
                rel_model = field_obj.remote_field.model
                if isinstance(rel_model, str):
                    if "." in rel_model:
                        t_app, t_name = rel_model.lower().split(".", 1)
                    else:
                        t_app, t_name = app_label, rel_model.lower()
                    parent_table = state.models[(t_app, t_name)].options["db_table"]
                else:
                    parent_table = rel_model._meta.db_table

                fks.append(
                    ForeignKeySpec(
                        child_table=table_name,
                        column=col_name,
                        parent_table=parent_table,
                        nullable=bool(field_obj.null),
                        one_to_one=is_o2o,
                        on_delete=getattr(
                            field_obj.remote_field.on_delete,
                            "__name__",
                            str(field_obj.remote_field.on_delete),
                        ),
                    )
                )

        if composite_pk:
            pk_tuple = composite_pk
        else:
            pk_tuple = tuple(pk_cols)

        tables[table_name] = TableSpec(
            app_label=app_label,
            name=table_name,
            pk_columns=pk_tuple,
            columns=columns,
        )

    return tables, fks


def verify_models_agree_with_migrations(migration_tables: dict[str, TableSpec]) -> list[str]:
    """Ensure live Django models match the migration ProjectState (tables + columns)."""
    errors: list[str] = []
    live_tables: dict[str, set[str]] = {}
    for app_label in OUR_APPS:
        for model in django_apps.get_app_config(app_label).get_models():
            cols = {
                f.column
                for f in model._meta.concrete_fields
                if getattr(f, "column", None) is not None
            }
            live_tables[model._meta.db_table] = cols

    if set(live_tables) != set(migration_tables):
        errors.append(
            f"Models vs migrations table mismatch: "
            f"only in models={sorted(set(live_tables) - set(migration_tables))}, "
            f"only in migrations={sorted(set(migration_tables) - set(live_tables))}"
        )
    for tname in sorted(set(live_tables) & set(migration_tables)):
        mig_cols = set(migration_tables[tname].columns)
        if live_tables[tname] != mig_cols:
            errors.append(
                f"Models vs migrations column mismatch on {tname}: "
                f"only in models={sorted(live_tables[tname] - mig_cols)}, "
                f"only in migrations={sorted(mig_cols - live_tables[tname])}"
            )
    return errors


ENTITY_RE = re.compile(
    r'^entity\s+"([^"]+)"\s+as\s+(\w+)(?:\s+<<([^>]+)>>)?\s*\{$'
)
COL_RE = re.compile(
    r'^(\*\s+)?(\w+)\s*:\s*([^<]+?)(?:\s+<<([^>]+)>>)?$'
)
EDGE_RE = re.compile(
    r'^(\w+)\s+(\|\||\|o|o\||o\{|\}o|\|\{|\}\|)'
    r'((?:-+(?:\[[^\]]+\])*-+)|(?:\.+(?:\[[^\]]+\])*\.+))'
    r'(\|\||\|o|o\||o\{|\}o|\|\{|\}\|)\s+(\w+)'
    r'(?:\s*:\s*"([^"]+)")?$'
)


def parse_puml_file(path: Path) -> tuple[list[ParsedEntity], list[ParsedEdge]]:
    """Parse entity declarations, columns, and crow's-foot edges from one .puml file."""
    entities: list[ParsedEntity] = []
    edges: list[ParsedEdge] = []
    alias_to_table: dict[str, str] = {}

    cur: ParsedEntity | None = None
    in_note = False
    in_legend = False
    in_skinparam_block = False
    in_style_block = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("'"):
            continue
        if line == "<style>":
            in_style_block = True
            continue
        if in_style_block:
            if line == "</style>":
                in_style_block = False
            continue
        if line.startswith("note "):
            in_note = True
            continue
        if in_note:
            if line == "end note":
                in_note = False
            continue
        if line.startswith("legend"):
            in_legend = True
            continue
        if in_legend:
            if line == "endlegend":
                in_legend = False
            continue
        if line.startswith("skinparam ") and line.endswith("{"):
            in_skinparam_block = True
            continue
        if in_skinparam_block:
            if line == "}":
                in_skinparam_block = False
            continue

        if cur is not None:
            if line == "}":
                entities.append(cur)
                cur = None
                continue
            if line == "--":
                continue
            cm = COL_RE.match(line)
            if not cm:
                raise ValueError(f"{path.name}:{lineno}: cannot parse column line: {line!r}")
            req = bool(cm.group(1))
            col_name = cm.group(2)
            col_type = cm.group(3).strip()
            tags = (
                {t.strip() for t in cm.group(4).split(",") if t.strip()}
                if cm.group(4)
                else set()
            )
            cur.columns[col_name] = ParsedColumn(
                name=col_name, required=req, puml_type=col_type, tags=tags
            )
            continue

        em = ENTITY_RE.match(line)
        if em:
            name, alias, stereo = em.group(1), em.group(2), em.group(3)
            stereos = {s.strip() for s in stereo.split(",")} if stereo else set()
            cur = ParsedEntity(
                name=name, alias=alias, stereotypes=stereos, source_file=path.name
            )
            alias_to_table[alias] = name
            continue

        rm = EDGE_RE.match(line)
        if rm:
            left_alias, left_card, connector, right_card, right_alias, label = rm.groups()
            dashed = "." in connector
            edges.append(
                ParsedEdge(
                    left=alias_to_table.get(left_alias, left_alias),
                    left_card=left_card,
                    dashed=dashed,
                    right_card=right_card,
                    right=alias_to_table.get(right_alias, right_alias),
                    label=label,
                    source_file=path.name,
                )
            )

    return entities, edges


def verify_diagram_set(
    label: str,
    paths: list[Path],
    tables: dict[str, TableSpec],
    fks: list[ForeignKeySpec],
) -> tuple[list[str], dict[str, ParsedEntity]]:
    """Verify one diagram or a partitioned set of area diagrams against migrations."""
    errors: list[str] = []
    owned_entities: dict[str, ParsedEntity] = {}
    ref_entities: list[ParsedEntity] = []
    all_edges: list[ParsedEdge] = []

    for path in paths:
        if not path.exists():
            errors.append(f"[{label}] Missing diagram file: {path}")
            continue
        ents, edges = parse_puml_file(path)
        all_edges.extend(edges)
        for ent in ents:
            if "ref" in ent.stereotypes:
                ref_entities.append(ent)
            else:
                if ent.name in owned_entities:
                    errors.append(
                        f"[{label}] Duplicate owned entity {ent.name!r} "
                        f"in {owned_entities[ent.name].source_file} and {ent.source_file}"
                    )
                owned_entities[ent.name] = ent

    # 1. Owned table coverage (exact 23 tables)
    expected_tables = set(tables)
    found_tables = set(owned_entities)
    if found_tables != expected_tables:
        missing = sorted(expected_tables - found_tables)
        extra = sorted(found_tables - expected_tables)
        errors.append(
            f"[{label}] Table set mismatch: missing={missing}, extra={extra}"
        )

    # 2. <<added>> stereotype matches exact 8 post-5-Nov tables
    expected_added = expected_tables - set(NOV5_TABLES)
    found_added = {t for t, ent in owned_entities.items() if "added" in ent.stereotypes}
    if found_added != expected_added:
        errors.append(
            f"[{label}] <<added>> tag mismatch: "
            f"missing={sorted(expected_added - found_added)}, "
            f"unexpected={sorted(found_added - expected_added)}"
        )

    # 3. External <<ref>> stubs must reference real tables and show only their PKs
    for ref in ref_entities:
        if ref.name not in tables:
            errors.append(f"[{label}] External stub {ref.name!r} in {ref.source_file} is not a real table")
            continue
        spec = tables[ref.name]
        if set(ref.columns) != set(spec.pk_columns):
            errors.append(
                f"[{label}] External stub {ref.name!r} in {ref.source_file} should show only PK "
                f"{spec.pk_columns}, got {sorted(ref.columns)}"
            )
        for pk_col in spec.pk_columns:
            pcol = ref.columns.get(pk_col)
            if pcol and (not pcol.required or "PK" not in pcol.tags):
                errors.append(
                    f"[{label}] External stub {ref.name}.{pk_col} must be required and <<PK>>"
                )

    # 4. Every owned entity's keys and displayed columns match migrations
    for tname, ent in sorted(owned_entities.items()):
        if tname not in tables:
            continue
        tspec = tables[tname]

        # Every PK and FK column must be shown
        for pk_col in tspec.pk_columns:
            if pk_col not in ent.columns:
                errors.append(f"[{label}] {tname}: missing PK column {pk_col!r}")
            else:
                pcol = ent.columns[pk_col]
                if "PK" not in pcol.tags or not pcol.required:
                    errors.append(f"[{label}] {tname}.{pk_col}: PK column must have * and <<PK>>")

        for col_name, cspec in tspec.columns.items():
            if cspec.is_fk and col_name not in ent.columns:
                errors.append(f"[{label}] {tname}: missing FK column {col_name!r}")

        # Every displayed column must exist and match nullability, type, and tags
        for col_name, pcol in ent.columns.items():
            if col_name not in tspec.columns:
                errors.append(
                    f"[{label}] {tname}.{col_name}: column does not exist in migrations "
                    f"(file: {ent.source_file})"
                )
                continue
            cspec = tspec.columns[col_name]
            if pcol.required != cspec.not_null:
                errors.append(
                    f"[{label}] {tname}.{col_name}: nullability mismatch "
                    f"(diagram required={pcol.required}, migration not_null={cspec.not_null})"
                )
            if pcol.puml_type != cspec.puml_type:
                errors.append(
                    f"[{label}] {tname}.{col_name}: type mismatch "
                    f"(diagram={pcol.puml_type!r}, migration={cspec.puml_type!r})"
                )
            if cspec.is_pk != ("PK" in pcol.tags):
                errors.append(
                    f"[{label}] {tname}.{col_name}: <<PK>> tag mismatch "
                    f"(diagram={'PK' in pcol.tags}, migration={cspec.is_pk})"
                )
            if cspec.is_fk != ("FK" in pcol.tags):
                errors.append(
                    f"[{label}] {tname}.{col_name}: <<FK>> tag mismatch "
                    f"(diagram={'FK' in pcol.tags}, migration={cspec.is_fk})"
                )
            if "unique" in pcol.tags and not cspec.is_unique:
                errors.append(
                    f"[{label}] {tname}.{col_name}: marked <<unique>> in diagram but not unique in migrations"
                )
            if cspec.is_fk and cspec.is_unique and "unique" not in pcol.tags:
                errors.append(
                    f"[{label}] {tname}.{col_name}: OneToOne/unique FK should carry <<unique>>"
                )

    # 5. Foreign keys (all 28 solid edges) and polymorphic links (all 4 dashed edges)
    solid_edges = [e for e in all_edges if not e.dashed]
    dashed_edges = [e for e in all_edges if e.dashed]

    # Index expected FKs by (parent, child, fk_column)
    expected_fk_map: dict[tuple[str, str, str], ForeignKeySpec] = {
        (fk.parent_table, fk.child_table, fk.column): fk for fk in fks
    }
    matched_fks: Counter[tuple[str, str, str]] = Counter()

    for edge in solid_edges:
        if not edge.label:
            errors.append(
                f"[{label}] Solid FK edge {edge.left} -- {edge.right} in {edge.source_file} "
                f"is missing an explicit FK column label"
            )
            continue

        # Support parent-left or parent-right orientation
        forward_key = (edge.left, edge.right, edge.label)
        reverse_key = (edge.right, edge.left, edge.label)
        if forward_key in expected_fk_map:
            fk = expected_fk_map[forward_key]
            parent_card, child_card = edge.left_card, edge.right_card
            key = forward_key
        elif reverse_key in expected_fk_map:
            fk = expected_fk_map[reverse_key]
            parent_card, child_card = edge.right_card, edge.left_card
            key = reverse_key
        else:
            errors.append(
                f"[{label}] Unrecognised solid FK edge in {edge.source_file}: "
                f"{edge.left} {edge.left_card}--{edge.right_card} {edge.right} : {edge.label!r}"
            )
            continue

        matched_fks[key] += 1

        # Verify parent-side optionality matches field.null
        expected_parent_cards = {"|o", "o|"} if fk.nullable else {"||"}
        if parent_card not in expected_parent_cards:
            errors.append(
                f"[{label}] FK {fk.child_table}.{fk.column} -> {fk.parent_table}: "
                f"parent cardinality {parent_card!r} disagrees with nullable={fk.nullable}"
            )

        # Verify child-side cardinality matches OneToOne vs ForeignKey
        expected_child_cards = {"o|", "|o"} if fk.one_to_one else {"o{", "}o"}
        if child_card not in expected_child_cards:
            errors.append(
                f"[{label}] FK {fk.child_table}.{fk.column} -> {fk.parent_table}: "
                f"child cardinality {child_card!r} disagrees with one_to_one={fk.one_to_one}"
            )

    for key in sorted(expected_fk_map):
        count = matched_fks[key]
        if count == 0:
            parent, child, col = key
            errors.append(f"[{label}] Missing FK edge: {child}.{col} -> {parent}")
        elif count > 1:
            parent, child, col = key
            errors.append(f"[{label}] Duplicate FK edge ({count}x): {child}.{col} -> {parent}")

    # Verify polymorphic dashed links
    found_poly: Counter[tuple[str, str]] = Counter()
    for edge in dashed_edges:
        pair = (edge.left, edge.right)
        rev = (edge.right, edge.left)
        if pair in EXPECTED_POLYMORPHIC_LINKS:
            found_poly[pair] += 1
        elif rev in EXPECTED_POLYMORPHIC_LINKS:
            found_poly[rev] += 1
        else:
            errors.append(
                f"[{label}] Unexpected dashed edge in {edge.source_file}: "
                f"{edge.left} .. {edge.right}"
            )
    for pair in sorted(EXPECTED_POLYMORPHIC_LINKS):
        if found_poly[pair] != 1:
            errors.append(
                f"[{label}] Polymorphic link {pair[0]} .. {pair[1]} expected 1x, found {found_poly[pair]}x"
            )

    return errors, owned_entities


def main() -> int:
    tables, fks = extract_migration_schema()
    all_errors: list[str] = []

    all_errors.extend(verify_models_agree_with_migrations(tables))

    combined_errors, combined_ents = verify_diagram_set(
        "combined", [COMBINED_DIAGRAM], tables, fks
    )
    all_errors.extend(combined_errors)

    split_errors, split_ents = verify_diagram_set(
        "four-area-split", AREA_DIAGRAMS, tables, fks
    )
    all_errors.extend(split_errors)

    # Cross-check that combined diagram and four-area split show the exact same columns per table
    for tname in sorted(set(combined_ents) & set(split_ents)):
        if combined_ents[tname].columns != split_ents[tname].columns:
            all_errors.append(
                f"[consistency] Column list differs between combined and area diagram for {tname}"
            )

    # Compute verified 5 November -> current delta
    new_tables = sorted(set(tables) - set(NOV5_TABLES))
    removed_tables = sorted(set(NOV5_TABLES) - set(tables))
    new_cols_on_existing: dict[str, list[str]] = {}
    removed_cols_on_existing: dict[str, list[str]] = {}
    for tname in sorted(set(tables) & set(NOV5_TABLES)):
        added = sorted(set(tables[tname].columns) - NOV5_TABLES[tname])
        removed = sorted(NOV5_TABLES[tname] - set(tables[tname].columns))
        if added:
            new_cols_on_existing[tname] = added
        if removed:
            removed_cols_on_existing[tname] = removed

    nov5_fk_count = sum(1 for fk in fks if fk.child_table in NOV5_TABLES)
    new_fk_count = sum(1 for fk in fks if fk.child_table not in NOV5_TABLES)

    by_area_tables = Counter(t.app_label for t in tables.values())
    by_area_fks = Counter(tables[fk.child_table].app_label for fk in fks)

    print("Schema verification against Django migrations (apps/*/migrations)")
    print("=" * 68)
    print(f"Tables:        {len(tables)} total (5 Nov: {len(NOV5_TABLES)}, +{len(new_tables)} added, -{len(removed_tables)} removed)")
    print(f"Foreign keys:  {len(fks)} total (5 Nov: {nov5_fk_count}, +{new_fk_count} added)")
    print(f"Polymorphic:   {len(EXPECTED_POLYMORPHIC_LINKS)} dashed source_type/source_id links")
    print()
    print("Breakdown by area:")
    for area in ("accounts", "documents", "meetings", "retrieval"):
        print(f"  - {area:10s}: {by_area_tables[area]:2d} tables, {by_area_fks[area]:2d} FKs")
    print()
    print(f"New tables since 5 Nov ({len(new_tables)}): {', '.join(new_tables)}")
    print("New columns on existing 5 Nov tables:")
    for tname, cols in new_cols_on_existing.items():
        print(f"  - {tname}: {', '.join(cols)}")
    if removed_cols_on_existing:
        print(f"Removed columns on existing tables: {removed_cols_on_existing}")
    print()

    if all_errors:
        print(f"FAILED with {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  ! {err}")
        return 1

    print("PASSED: Models agree with migrations.")
    print(f"PASSED: {COMBINED_DIAGRAM.relative_to(REPO_ROOT)} matches all {len(tables)} tables, {len(fks)} FKs, and {len(EXPECTED_POLYMORPHIC_LINKS)} polymorphic links.")
    print(f"PASSED: 4-area split ({len(AREA_DIAGRAMS)} files) matches all {len(tables)} tables, {len(fks)} FKs, and {len(EXPECTED_POLYMORPHIC_LINKS)} polymorphic links.")
    print("PASSED: Combined diagram and 4-area split show identical columns per table.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
