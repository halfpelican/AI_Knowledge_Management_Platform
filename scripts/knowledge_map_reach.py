"""How far a walk reaches on the reference corpus: the measurement behind FR-20's two caps (D-132).

    python scripts/knowledge_map_reach.py

FR-20 caps the knowledge map's traversal depth and its returned node count, and the proposal gives
both as "To be tuned" against no objective. D-132 fixes them by a stated rule, and this script is
the measurement that rule reads. It needs no database and no Django: it reads only
``corpus/objective-02/manifest.json``, the committed description of the reference corpus, and
builds the graph FR-20 would build from it for each role:

- a node for each document and transcript the role may read (the manifest's ``invalid`` items are
  left out: they are the upload refusals, and the three of them that are stored carry no tag);
- a node for each tag on those documents, and an edge from the document to it;
- a node for each uploader of those documents, and an edge from the uploader to the document.

No transcript in the manifest carries a tag and nothing in the loaders writes an attendee, so on
this corpus a meeting is a node with no edge. The script prints, per role, the size of the whole
map and how many nodes a walk of one, two and three hops reaches from each start node.

What it does not measure: any other corpus, the alpha's database, or attendance. It reads a file;
it does not call the application, so a change to ``apps/api/knowledge_map.py`` does not move it.
"""

import json
import statistics
from collections import defaultdict
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / "corpus" / "objective-02" / "manifest.json"

# Who reads what, as apps/core/constants.py EFFECTIVE_ROLES has it (D-66). Written out here so
# that the script stays free of Django; it is two lines, and the manifest's own
# ``visible_to_roles`` values are these role names.
EFFECTIVE_ROLES = {
    "Employee": ("Employee",),
    "Administrator": ("Administrator", "Employee"),
}
SOURCE_KINDS = ("document", "transcript")
DEPTHS = (1, 2, 3)


def graph_for(items, role):
    """The nodes and edges of the role's map: sources in scope, their tags and their uploaders."""
    nodes, edges = set(), set()
    for item in items:
        if not set(item["visible_to_roles"]) & set(EFFECTIVE_ROLES[role]):
            continue
        source = ("source", item["id"])
        nodes.add(source)
        if item["kind"] != "document":
            continue
        uploader = ("contributor", item["uploader"])
        nodes.add(uploader)
        edges.add((source, uploader))
        for dimension, names in (item.get("tags") or {}).items():
            for name in names:
                tag = ("tag", dimension, name)
                nodes.add(tag)
                edges.add((source, tag))
    return nodes, edges


def reach(edges, start, depth):
    """How many nodes a walk of ``depth`` hops from ``start`` holds, the start included."""
    neighbours = defaultdict(set)
    for left, right in edges:
        neighbours[left].add(right)
        neighbours[right].add(left)
    seen, ring = {start}, [start]
    for _ in range(depth):
        ring = [node for held in ring for node in sorted(neighbours[held]) if node not in seen]
        seen.update(ring)
    return len(seen)


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = [item for item in manifest["items"] if item["kind"] in SOURCE_KINDS]
    for role in EFFECTIVE_ROLES:
        nodes, edges = graph_for(items, role)
        kinds = defaultdict(int)
        for node in nodes:
            kinds[node[0]] += 1
        print(f"{role}: {len(nodes)} nodes "
              f"(sources {kinds['source']}, tags {kinds['tag']}, contributors {kinds['contributor']}), "
              f"{len(edges)} edges")
        for depth in DEPTHS:
            sizes = sorted(reach(edges, node, depth) for node in nodes)
            print(f"  {depth} hop{'s' if depth > 1 else ''}: from one start, "
                  f"min {sizes[0]}, median {statistics.median(sizes):g}, max {sizes[-1]} "
                  f"of {len(nodes)}")


if __name__ == "__main__":
    main()
