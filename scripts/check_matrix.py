"""Enforce the feature matrix: every listed test id must be collected by pytest."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "tests" / "FEATURE_MATRIX.md"


def main() -> int:
    text = MATRIX.read_text(encoding="utf-8")
    ids = set(re.findall(r"tests/[\w/]+\.py::[\w_]+", text))
    if not ids:
        print("no test ids found in matrix")
        return 2

    cp = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    if cp.returncode not in (0, 5):
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        return cp.returncode

    # pytest --collect-only -q outputs one line per test id, possibly with
    # parametrization suffix [param]. We strip the [param] suffix when
    # comparing matrix ids (which name the function, not parametrization).
    collected = set()
    for line in cp.stdout.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        # Drop any " " or "[" annotation
        if "[" in line:
            line = line.split("[", 1)[0]
        # On Windows, pytest may use forward slashes already; normalize anyway
        line = line.replace("\\", "/")
        collected.add(line)

    missing = sorted(tid for tid in ids if tid not in collected)
    if missing:
        print("MATRIX: missing tests:")
        for m in missing:
            print(f"  {m}")
        return 1
    print(f"MATRIX: {len(ids)} feature rows, all collected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
