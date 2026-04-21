"""Enforce the feature matrix bidirectionally.

1. Every test id listed in FEATURE_MATRIX.md must be collected by pytest.
2. Every test id collected by pytest must appear in FEATURE_MATRIX.md
   OR carry the `@pytest.mark.matrix_exempt` marker.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "tests" / "FEATURE_MATRIX.md"


def _normalize(line: str) -> str:
    if "[" in line:
        line = line.split("[", 1)[0]
    return line.replace("\\", "/").strip()


def _collect_all() -> set[str]:
    cp = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    if cp.returncode not in (0, 5):
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        raise SystemExit(cp.returncode)
    out = set()
    for raw in cp.stdout.splitlines():
        s = _normalize(raw)
        if "::" in s:
            out.add(s)
    return out


def _collect_exempt() -> set[str]:
    cp = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only",
         "-m", "matrix_exempt"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    # Exit 5 = no tests selected, treat as empty.
    if cp.returncode not in (0, 5):
        # Unknown mark warnings still print; only treat hard errors as fatal.
        print(cp.stderr, file=sys.stderr)
    out = set()
    for raw in cp.stdout.splitlines():
        s = _normalize(raw)
        if "::" in s:
            out.add(s)
    return out


def main() -> int:
    text = MATRIX.read_text(encoding="utf-8")
    matrix_ids = set(re.findall(r"tests/[\w/]+\.py::[\w_]+", text))
    if not matrix_ids:
        print("no test ids found in matrix")
        return 2

    collected = _collect_all()
    exempt = _collect_exempt()

    missing_from_collection = sorted(matrix_ids - collected)
    if missing_from_collection:
        print("MATRIX: tests listed in matrix but NOT collected by pytest:")
        for m in missing_from_collection:
            print(f"  {m}")
        return 1

    unaccounted = sorted(collected - matrix_ids - exempt)
    if unaccounted:
        print("MATRIX: tests collected but NOT in matrix and not @pytest.mark.matrix_exempt:")
        for m in unaccounted:
            print(f"  {m}")
        return 1

    print(f"MATRIX: {len(matrix_ids)} feature rows, "
          f"{len(collected)} collected tests, {len(exempt)} exempt — "
          f"all accounted for.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
