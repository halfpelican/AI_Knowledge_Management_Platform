"""How long the Topic values in the recorded Objective 05 runs are, and how long their replies were
(D-133, 15 November 2026).

D-133 sizes the reject route's bound, MAXIMUM_PROPOSED_TAG_LENGTH, for the longest classification
reply either provider may return, and calls a proposal longer than it a residual "far from anything
measured". This is the measurement behind that phrase. It reads the records already committed under
corpus/objective-05/runs/ and nothing else: no database, no provider, no network.

- **Topic values:** every JSON object, in every .json or .jsonl file under the runs folder, whose
  ``dimension`` is "Topic" and which carries a string ``value`` (a suggestion or a proposal) or
  ``name`` (a link). Reported per run folder: how many, and the longest.
- **Replies:** every ``attempts.log`` line's ``max_tokens=`` and ``completion_tokens=``. Reported
  per run folder: the ceilings sent, and the longest reply in completion tokens.

Run from the repository root (standard library only):

    .venv\\Scripts\\python.exe corpus\\objective-05\\runs\\2026-11-15-topic-lengths\\topic_lengths.py `
        > corpus\\objective-05\\runs\\2026-11-15-topic-lengths\\topic-lengths.txt

The output is sorted, so a second run over the same records is identical.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE.parent  # corpus/objective-05/runs
TOPIC = "Topic"
MAX_TOKENS = re.compile(r"\bmax_tokens=(\d+)")
COMPLETION_TOKENS = re.compile(r"\bcompletion_tokens=(\d+)")


def records(path: Path):
    """The JSON documents in ``path``: the whole file, or one per line of a JSON Lines file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        yield json.loads(text)
        return
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def topic_values(node):
    """Every Topic value or name in ``node``, depth first."""
    if isinstance(node, dict):
        if node.get("dimension") == TOPIC:
            value = node.get("value") if isinstance(node.get("value"), str) else node.get("name")
            if isinstance(value, str):
                yield value
        for child in node.values():
            yield from topic_values(child)
    elif isinstance(node, list):
        for child in node:
            yield from topic_values(child)


def run_folder(path: Path) -> str:
    return path.relative_to(RUNS).parts[0]


def main():
    topics: dict[str, list[int]] = {}
    for path in sorted(RUNS.rglob("*")):
        if HERE in path.parents or path.suffix not in (".json", ".jsonl") or not path.is_file():
            continue
        for record in records(path):
            for value in topic_values(record):
                topics.setdefault(run_folder(path), []).append(len(value))

    ceilings: dict[str, set[int]] = {}
    longest_reply: dict[str, int] = {}
    for path in sorted(RUNS.rglob("attempts.log")):
        folder = run_folder(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        ceilings.setdefault(folder, set()).update(int(n) for n in MAX_TOKENS.findall(text))
        replies = [int(n) for n in COMPLETION_TOKENS.findall(text)]
        if replies:
            longest_reply[folder] = max(longest_reply.get(folder, 0), max(replies))

    print("Topic values (suggestions, proposals and links) in corpus/objective-05/runs/")
    for folder in sorted(topics):
        lengths = topics[folder]
        print(f"  {folder}: {len(lengths)} values, the longest {max(lengths)} characters")
    every = [length for lengths in topics.values() for length in lengths]
    print(f"  all runs: {len(every)} values, the longest {max(every)} characters")
    print()
    print("Classification replies in the runs' attempts.log files")
    for folder in sorted(ceilings):
        sent = ", ".join(str(n) for n in sorted(ceilings[folder])) or "none recorded"
        reply = longest_reply.get(folder)
        reply_text = f"{reply} completion tokens" if reply is not None else "none recorded"
        print(f"  {folder}: max_tokens sent {sent}; the longest reply {reply_text}")


if __name__ == "__main__":
    main()
