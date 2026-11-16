"""The port's rows query against real PowerShell, on this laptop (D-87's note of 12 November 2026, 13 November).

No test runs the PowerShell itself: the tests script each lookup's output. The re-audit on
``bbbda8c`` found by reading the code that the rows query in ``scripts/server_record.py`` ran with
``-ErrorAction SilentlyContinue`` and always exited 0, so a query that failed inside PowerShell read
as "no rows". This runs ``_port_row_owners`` for real, as the script now has it and as it was at
``bbbda8c``, in four stages on a scratch loopback port:

1. **Nothing on the port:** the query must exit 0, print ``[]``, and read as no owner, not as unread.
2. **One listener,** ``python -m http.server``: the query must name it.
3. **A query that fails inside PowerShell,** made by asking for a CIM class that does not exist:
   the query as it now is must exit non-zero and read as unread.
4. **The same failing query, as the script was at ``bbbda8c``** (taken from git, not retyped): it
   exited 0 and printed ``[]``, and so read as no owner.

Stages 3 and 4 change only the class name in the PowerShell text, in this process, through a
wrapper around ``subprocess.run`` that records each command's exit code and output and otherwise
calls the real one. It touches no database, no project server and no process it did not start; the
listener is started and stopped by ``try_strict_lookup.py``'s own helpers. Standard library only.

Usage, from the repository root, in PowerShell::

    & $py corpus\\objective-02\\runs\\2026-11-12-listener-lookup\\check_rows_query.py 8772
"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[3]  # corpus/objective-02/runs/<this folder>/<this file>
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
import server_record  # noqa: E402

REAL_CLASS = "MSFT_NetTCPConnection"
MISSING_CLASS = "MSFT_NoSuchClassForThisCheck"


def say(text: str) -> None:
    print(text, flush=True)


def load_trial():
    spec = importlib.util.spec_from_file_location("try_strict_lookup", HERE / "try_strict_lookup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_at(commit: str) -> types.ModuleType:
    """scripts/server_record.py as it was at ``commit``, read from git, as a module of its own."""
    source = subprocess.run(["git", "show", f"{commit}:scripts/server_record.py"], cwd=REPOSITORY_ROOT,
                            capture_output=True, text=True, encoding="utf-8", check=True).stdout
    module = types.ModuleType(f"server_record_at_{commit}")
    module.__file__ = str(REPOSITORY_ROOT / "scripts" / "server_record.py")
    sys.modules[module.__name__] = module
    exec(compile(source, f"server_record.py@{commit}", "exec"), module.__dict__)
    return module


def rows(module: types.ModuleType, port: int, *, break_the_class: bool) -> None:
    """Run ``module._port_row_owners(port)`` with the real subprocess.run, and say what happened."""
    seen = {}

    def run(command, **kwargs):
        if break_the_class:
            assert command[-1].count(REAL_CLASS) == 1
            command = [*command[:-1], command[-1].replace(REAL_CLASS, MISSING_CLASS)]
        completed = subprocess.run(command, **kwargs)
        seen.update(exit=completed.returncode, stdout=(completed.stdout or "").strip())
        return completed

    real = module.subprocess
    module.subprocess = types.SimpleNamespace(run=run, TimeoutExpired=subprocess.TimeoutExpired)
    try:
        owners, why = module._port_row_owners(port)
    finally:
        module.subprocess = real
    say(f"  PowerShell exit code: {seen['exit']}; printed: {seen['stdout'][:160] or '(nothing)'}")
    say(f"  read as: owners {[(owner['pid'], owner['states']) for owner in owners]}; unread: {why or 'no'}")


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8772
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPOSITORY_ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    say(f"port {port}, platform {sys.platform}, python {sys.version.split()[0]}, commit {commit}")
    trial = load_trial()
    old = load_at("bbbda8c")

    say("--- 1. nothing on the port, the query as it now is ---")
    rows(server_record, port, break_the_class=False)
    child = trial.start(port)
    try:
        say("--- 2. one listener, the query as it now is ---")
        rows(server_record, port, break_the_class=False)
    finally:
        trial.stop([child], port)
    say(f"--- 3. a query that fails inside PowerShell (class {MISSING_CLASS}), the query as it now is ---")
    rows(server_record, port, break_the_class=True)
    say(f"--- 4. the same failing query, the query as it was at bbbda8c ---")
    rows(old, port, break_the_class=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
