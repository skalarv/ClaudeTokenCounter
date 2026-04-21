# TokenFollow Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an always-on-top Windows overlay showing Claude Code token usage (5h window + weekly Opus + weekly Sonnet) plus current GPU utilization, refreshed every 10 s.

**Architecture:** Single Python package `tokenfollow/` with five focused modules (parser, aggregator, budget, gpu, ui) and a thin entry point `token_follow.py`. Pure logic is separated from tkinter UI so tests can cover ≥97 % line+branch coverage without a display server.

**Tech Stack:** Python 3.8+ stdlib only at runtime (`tkinter`, `json`, `pathlib`, `datetime`, `logging`, `subprocess`). Test-only: `pytest`, `pytest-cov`, `freezegun`.

**Spec:** `docs/superpowers/specs/2026-04-21-tokenfollow-overlay-design.md`

---

## File Structure

Files created over the course of this plan:

```
G:\GitWorkSpace\TokenFollow\
├── token_follow.py
├── TokenFollow.bat
├── run_tests.bat
├── pyproject.toml
├── .coveragerc
├── README.md
├── tokenfollow\
│   ├── __init__.py
│   ├── parser.py
│   ├── aggregator.py
│   ├── budget.py
│   ├── gpu.py
│   └── ui.py
├── scripts\
│   └── check_matrix.py
└── tests\
    ├── __init__.py
    ├── conftest.py
    ├── FEATURE_MATRIX.md
    ├── fixtures\
    │   ├── fresh.jsonl
    │   ├── mid_window.jsonl
    │   ├── opus_near_cap.jsonl
    │   └── after_idle.jsonl
    ├── test_parser.py
    ├── test_aggregator.py
    ├── test_budget.py
    ├── test_gpu.py
    ├── test_ui_smoke.py
    └── test_integration.py
```

Responsibility split:
- `parser.py`: JSONL I/O, incremental offset cache, line → `UsageRecord` conversion.
- `aggregator.py`: pure functions over `list[UsageRecord]` → `Snapshot`. No I/O.
- `budget.py`: `config.json` read/write, hybrid budget math, window position.
- `gpu.py`: subprocess-only GPU utilization reader with source auto-detect.
- `ui.py`: tkinter rendering only; consumes `Snapshot`, calls close/save callbacks.
- `token_follow.py`: wires the five together on a 10 s tick loop.

---

## Task 0: Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.coveragerc`
- Create: `tokenfollow/__init__.py` (empty)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "tokenfollow"
version = "0.1.0"
description = "Always-on-top Claude Code usage + GPU overlay for Windows"
requires-python = ">=3.8"

[project.optional-dependencies]
dev = ["pytest>=7", "pytest-cov>=4", "freezegun>=1.2"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Create `.coveragerc`**

```ini
[run]
branch = True
source = tokenfollow

[report]
fail_under = 97
show_missing = True
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

- [ ] **Step 3: Create empty package and test init files**

`tokenfollow/__init__.py` and `tests/__init__.py` — both literally empty (0 bytes).

- [ ] **Step 4: Create `tests/conftest.py` with shared fixtures**

```python
"""Shared pytest fixtures for TokenFollow tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest


def _jsonl_line(ts: datetime, model: str, input_t: int = 100,
                cache_create: int = 0, cache_read: int = 0,
                output_t: int = 50) -> str:
    """Build a single JSONL line mimicking Claude Code's assistant-message shape."""
    return json.dumps({
        "type": "assistant",
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_t,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_t,
                "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
            },
        },
    })


@pytest.fixture
def make_jsonl(tmp_path: Path):
    """Factory: write a JSONL file with given records and return its path."""
    def _factory(name: str, records: Iterable[dict]) -> Path:
        lines = []
        for r in records:
            lines.append(_jsonl_line(
                ts=r["ts"],
                model=r.get("model", "claude-sonnet-4-6"),
                input_t=r.get("input", 100),
                cache_create=r.get("cache_create", 0),
                cache_read=r.get("cache_read", 0),
                output_t=r.get("output", 50),
            ))
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p
    return _factory


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """Empty fake ~/.claude/projects root."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture
def utc():
    """Shorthand for building UTC datetimes: utc(2026, 4, 21, 10, 0)."""
    def _make(*args) -> datetime:
        return datetime(*args, tzinfo=timezone.utc)
    return _make
```

- [ ] **Step 5: Verify scaffolding**

Run: `pytest --collect-only` from `G:\GitWorkSpace\TokenFollow\`
Expected: exits 0 with "no tests collected" (or similar).

- [ ] **Step 6: Commit**

```bash
git init
git add pyproject.toml .coveragerc tokenfollow/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold tokenfollow package and pytest config"
```

---

## Task 1: UsageRecord dataclass + parse one line

**Files:**
- Create: `tokenfollow/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_parser.py
from __future__ import annotations

from datetime import datetime, timezone

from tokenfollow.parser import UsageRecord, parse_line


def test_parse_valid_line():
    line = (
        '{"type":"assistant","timestamp":"2026-04-21T10:00:00Z",'
        '"message":{"model":"claude-opus-4-7",'
        '"usage":{"input_tokens":10,"cache_creation_input_tokens":200,'
        '"cache_read_input_tokens":1000,"output_tokens":50}}}'
    )
    rec = parse_line(line)
    assert rec == UsageRecord(
        ts=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
        model="claude-opus-4-7",
        input=10, cache_create=200, cache_read=1000, output=50,
    )
```

- [ ] **Step 2: Run test — expect failure**

Run: `pytest tests/test_parser.py::test_parse_valid_line -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tokenfollow.parser'`.

- [ ] **Step 3: Minimal implementation**

```python
# tokenfollow/parser.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class UsageRecord:
    ts: datetime
    model: str
    input: int
    cache_create: int
    cache_read: int
    output: int


def _parse_ts(raw: str) -> datetime:
    # Accept both "...Z" and "...+00:00"
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_line(line: str) -> UsageRecord | None:
    """Parse one JSONL line; return None if malformed or not an assistant usage record."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    msg = obj.get("message") or {}
    usage = msg.get("usage")
    ts_raw = obj.get("timestamp")
    model = msg.get("model")
    if not (usage and ts_raw and model):
        return None
    try:
        ts = _parse_ts(ts_raw)
    except ValueError:
        return None
    return UsageRecord(
        ts=ts,
        model=model,
        input=int(usage.get("input_tokens", 0)),
        cache_create=int(usage.get("cache_creation_input_tokens", 0)),
        cache_read=int(usage.get("cache_read_input_tokens", 0)),
        output=int(usage.get("output_tokens", 0)),
    )
```

- [ ] **Step 4: Run test — expect pass**

Run: `pytest tests/test_parser.py::test_parse_valid_line -v`
Expected: PASS.

- [ ] **Step 5: Add the malformed-line test**

```python
# append to tests/test_parser.py
import pytest


@pytest.mark.parametrize("line", [
    "",
    "{not json",
    '{"type":"assistant"}',                                     # no message
    '{"type":"assistant","message":{}}',                        # no usage
    '{"timestamp":"2026-04-21T10:00:00Z","message":{"usage":{}}}',  # no model
    '{"timestamp":"not-a-date","message":{"model":"x","usage":{"input_tokens":1}}}',
])
def test_skip_malformed(line):
    assert parse_line(line) is None
```

- [ ] **Step 6: Run the new test — expect pass (implementation already handles these)**

Run: `pytest tests/test_parser.py -v`
Expected: both tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tokenfollow/parser.py tests/test_parser.py
git commit -m "feat(parser): parse single JSONL usage line with malformed-line tolerance"
```

---

## Task 2: UsageParser — walk projects, incremental re-read

**Files:**
- Modify: `tokenfollow/parser.py`
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Write the incremental-reread test**

```python
# append to tests/test_parser.py
from pathlib import Path

from tokenfollow.parser import UsageParser


def test_incremental_reread(projects_root: Path, make_jsonl, utc):
    proj = projects_root / "ProjectA"
    proj.mkdir()
    f = proj / "session1.jsonl"
    f.write_text(
        # first line
        '{"timestamp":"2026-04-21T10:00:00Z","message":{"model":"claude-sonnet-4-6",'
        '"usage":{"input_tokens":1,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":2}}}\n',
        encoding="utf-8",
    )

    parser = UsageParser(projects_root)
    first = parser.scan()
    assert len(first) == 1

    # append a second line
    with f.open("a", encoding="utf-8") as h:
        h.write(
            '{"timestamp":"2026-04-21T10:01:00Z","message":{"model":"claude-sonnet-4-6",'
            '"usage":{"input_tokens":3,"cache_creation_input_tokens":0,'
            '"cache_read_input_tokens":0,"output_tokens":4}}}\n'
        )

    second = parser.scan()
    assert len(second) == 2
    assert second[0].input == 1
    assert second[1].input == 3
```

- [ ] **Step 2: Write the truncation / rotation test**

```python
# append to tests/test_parser.py
def test_truncation_resets_offset(projects_root: Path):
    proj = projects_root / "ProjectA"
    proj.mkdir()
    f = proj / "session.jsonl"
    f.write_text(
        '{"timestamp":"2026-04-21T10:00:00Z","message":{"model":"claude-sonnet-4-6",'
        '"usage":{"input_tokens":1,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":2}}}\n',
        encoding="utf-8",
    )
    parser = UsageParser(projects_root)
    assert len(parser.scan()) == 1

    # shrink the file (simulate rotation)
    f.write_text("", encoding="utf-8")
    f.write_text(
        '{"timestamp":"2026-04-21T11:00:00Z","message":{"model":"claude-opus-4-7",'
        '"usage":{"input_tokens":9,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":1}}}\n',
        encoding="utf-8",
    )
    result = parser.scan()
    # After truncation, offset resets and we re-read the new line only.
    assert len(result) == 2                  # original kept + new one
    assert result[-1].model == "claude-opus-4-7"
```

- [ ] **Step 3: Write the missing-dir and empty-dir tests**

```python
# append to tests/test_parser.py
def test_missing_projects_dir_is_ok(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    parser = UsageParser(missing)
    assert parser.scan() == []


def test_empty_projects_dir(projects_root: Path):
    parser = UsageParser(projects_root)
    assert parser.scan() == []
```

- [ ] **Step 4: Run tests — expect failure**

Run: `pytest tests/test_parser.py -v`
Expected: the three new tests fail with `AttributeError: ... UsageParser` or `ImportError`.

- [ ] **Step 5: Implement `UsageParser`**

Append to `tokenfollow/parser.py`:

```python
from pathlib import Path
from typing import Dict, List


class UsageParser:
    """Walks <projects_root>/**/*.jsonl, reading only new bytes since last scan.

    Offsets are held in memory for the lifetime of the process. On first scan
    every file is read from byte 0; thereafter only the tail past the stored
    offset is read. If a file shrinks between scans it is treated as rotated
    and re-read from 0.
    """

    def __init__(self, projects_root: Path):
        self._root = Path(projects_root)
        self._offsets: Dict[Path, int] = {}
        self._records: List[UsageRecord] = []

    def scan(self) -> List[UsageRecord]:
        if not self._root.exists():
            return list(self._records)
        for path in sorted(self._root.rglob("*.jsonl")):
            try:
                size = path.stat().st_size
            except OSError:
                continue
            prev = self._offsets.get(path, 0)
            if size < prev:                       # truncation / rotation
                prev = 0
            if size == prev:
                continue
            try:
                with path.open("rb") as f:
                    f.seek(prev)
                    data = f.read(size - prev)
            except OSError:
                continue
            self._offsets[path] = size
            for raw in data.splitlines():
                if not raw.strip():
                    continue
                try:
                    line = raw.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    continue
                rec = parse_line(line)
                if rec is not None:
                    self._records.append(rec)
        self._records.sort(key=lambda r: r.ts)
        return list(self._records)

    def save_cache(self, cache_path: Path) -> None:
        """Write current offsets to disk (diagnostic only; not read on startup)."""
        payload = {str(p): off for p, off in self._offsets.items()}
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 6: Run tests — expect pass**

Run: `pytest tests/test_parser.py -v`
Expected: all 5+ tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tokenfollow/parser.py tests/test_parser.py
git commit -m "feat(parser): walk projects root with incremental reread"
```

---

## Task 3: Aggregator — 5h window math

**Files:**
- Create: `tokenfollow/aggregator.py`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Write the empty-records test**

```python
# tests/test_aggregator.py
from __future__ import annotations

from datetime import timedelta

from tokenfollow.aggregator import aggregate, Snapshot, WindowSnapshot
from tokenfollow.parser import UsageRecord


def _rec(ts, model="claude-sonnet-4-6", input=100, cache_create=0,
         cache_read=0, output=50) -> UsageRecord:
    return UsageRecord(ts=ts, model=model, input=input,
                       cache_create=cache_create, cache_read=cache_read, output=output)


BUDGETS = {"5h": 88_000_000, "week_opus": 70_000_000, "week_sonnet": 440_000_000}
OBSERVED = {"5h": 0, "week_opus": 0, "week_sonnet": 0}
WEIGHTS = {"cache_read": 0.1}


def test_empty_records(utc):
    snap = aggregate([], BUDGETS, OBSERVED, utc(2026, 4, 21, 12, 0), WEIGHTS)
    assert snap.five_hour.used == 0
    assert snap.five_hour.resets_at is None
    assert snap.week_opus.used == 0
    assert snap.week_sonnet.used == 0
```

- [ ] **Step 2: Write the 5h anchor + boundary tests**

```python
# append to tests/test_aggregator.py
def test_window_anchor_after_gap(utc):
    records = [
        _rec(utc(2026, 4, 21,  8, 0), input=10),   # anchors first window
        _rec(utc(2026, 4, 21, 12, 0), input=20),   # 4h later, same window
        _rec(utc(2026, 4, 21, 17, 1), input=30),   # 5h1m after prev → new window
    ]
    now = utc(2026, 4, 21, 18, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    # Only the 17:01 record is in the current window.
    assert snap.five_hour.used == 30 + 50   # input + output, no cache
    assert snap.five_hour.resets_at == utc(2026, 4, 21, 17, 1) + timedelta(hours=5)


def test_exactly_5h_gap_starts_new_window(utc):
    records = [
        _rec(utc(2026, 4, 21,  8, 0), input=10),
        _rec(utc(2026, 4, 21, 13, 0), input=20),   # exactly 5h later → new window
    ]
    now = utc(2026, 4, 21, 13, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.five_hour.used == 20 + 50
    assert snap.five_hour.resets_at == utc(2026, 4, 21, 18, 0)


def test_no_active_window_when_idle(utc):
    records = [_rec(utc(2026, 4, 21, 8, 0), input=10)]
    now = utc(2026, 4, 21, 14, 0)                   # 6h after last record
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.five_hour.used == 0
    assert snap.five_hour.resets_at is None
```

- [ ] **Step 3: Run — expect failure**

Run: `pytest tests/test_aggregator.py -v`
Expected: ImportError / FAIL on the new module.

- [ ] **Step 4: Implement aggregator (5h window first, weekly stubs return zero)**

```python
# tokenfollow/aggregator.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Mapping, Optional

from tokenfollow.parser import UsageRecord


FIVE_HOURS = timedelta(hours=5)
ONE_WEEK = timedelta(days=7)


@dataclass
class WindowSnapshot:
    used: int
    budget: int
    resets_at: Optional[datetime]
    observed_max: int


@dataclass
class Snapshot:
    five_hour: WindowSnapshot
    week_opus: WindowSnapshot
    week_sonnet: WindowSnapshot
    now: datetime
    gpu_percent: Optional[int] = None


def _counted(rec: UsageRecord, weights: Mapping[str, float]) -> int:
    cr = weights.get("cache_read", 0.1)
    return int(rec.input + rec.cache_create + round(rec.cache_read * cr) + rec.output)


def _family(model: str) -> str:
    if model.startswith("claude-opus"):
        return "opus"
    if model.startswith("claude-sonnet"):
        return "sonnet"
    if model.startswith("claude-haiku"):
        return "haiku"
    return "other"


def _current_5h_window(records: List[UsageRecord], now: datetime):
    """Return (anchor_ts, [records in window]) or (None, [])."""
    if not records:
        return None, []
    anchor = records[0].ts
    windows = [[records[0]]]
    for rec in records[1:]:
        if rec.ts - windows[-1][-1].ts >= FIVE_HOURS:
            windows.append([rec])
        else:
            windows[-1].append(rec)
    for win in reversed(windows):
        anchor = win[0].ts
        if anchor <= now < anchor + FIVE_HOURS:
            return anchor, win
    return None, []


def aggregate(records: List[UsageRecord],
              budgets: Mapping[str, int],
              observed: Mapping[str, int],
              now: datetime,
              weights: Mapping[str, float]) -> Snapshot:
    records = sorted(records, key=lambda r: r.ts)

    anchor, win_records = _current_5h_window(records, now)
    five_used = sum(_counted(r, weights) for r in win_records)
    five = WindowSnapshot(
        used=five_used,
        budget=max(budgets["5h"], observed["5h"], five_used),
        resets_at=(anchor + FIVE_HOURS) if anchor else None,
        observed_max=observed["5h"],
    )

    # weekly stubs for now — filled in Task 4
    empty = WindowSnapshot(used=0, budget=budgets["week_opus"],
                           resets_at=None, observed_max=observed["week_opus"])
    empty2 = WindowSnapshot(used=0, budget=budgets["week_sonnet"],
                            resets_at=None, observed_max=observed["week_sonnet"])
    return Snapshot(five_hour=five, week_opus=empty, week_sonnet=empty2, now=now)
```

- [ ] **Step 5: Run — expect pass**

Run: `pytest tests/test_aggregator.py -v`
Expected: the three 5h tests PASS. (Weekly tests come in Task 4.)

- [ ] **Step 6: Commit**

```bash
git add tokenfollow/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): 5h rolling window with gap-based anchoring"
```

---

## Task 4: Aggregator — weekly rolling + model families + cache-read weight

**Files:**
- Modify: `tokenfollow/aggregator.py`
- Modify: `tests/test_aggregator.py`

- [ ] **Step 1: Write the weekly + family tests**

```python
# append to tests/test_aggregator.py
def test_weekly_split_by_family(utc):
    records = [
        _rec(utc(2026, 4, 15, 10, 0), model="claude-opus-4-7",    input=1000, output=100),
        _rec(utc(2026, 4, 16, 10, 0), model="claude-sonnet-4-6",  input=2000, output=200),
        _rec(utc(2026, 4, 17, 10, 0), model="claude-haiku-4-5",   input=300,  output=30),
        _rec(utc(2026, 4,  5, 10, 0), model="claude-opus-4-7",    input=9999, output=9999),  # > 7d ago
    ]
    now = utc(2026, 4, 21, 12, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.week_opus.used == 1000 + 100
    # sonnet bar absorbs haiku
    assert snap.week_sonnet.used == (2000 + 200) + (300 + 30)


def test_cache_read_weight(utc):
    records = [_rec(utc(2026, 4, 21, 11, 0), model="claude-opus-4-7",
                    input=0, cache_read=1000, output=0)]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, {"cache_read": 0.1})
    assert snap.five_hour.used == 100       # 1000 * 0.1


def test_weekly_resets_at_oldest_plus_7d(utc):
    records = [
        _rec(utc(2026, 4, 16, 10, 0), model="claude-opus-4-7", input=1),
        _rec(utc(2026, 4, 20, 10, 0), model="claude-opus-4-7", input=2),
    ]
    now = utc(2026, 4, 21, 10, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.week_opus.resets_at == utc(2026, 4, 16, 10, 0) + timedelta(days=7)


def test_unknown_model_ignored_in_weekly(utc):
    records = [_rec(utc(2026, 4, 20, 10, 0), model="custom-local-llm", input=1000)]
    now = utc(2026, 4, 21, 10, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.week_opus.used == 0
    assert snap.week_sonnet.used == 0
```

- [ ] **Step 2: Run — expect failure**

Run: `pytest tests/test_aggregator.py -v`
Expected: 4 new tests FAIL.

- [ ] **Step 3: Replace the weekly stubs with real logic**

In `tokenfollow/aggregator.py`, replace the `# weekly stubs` block plus the last `return` with:

```python
    cutoff = now - ONE_WEEK
    recent = [r for r in records if r.ts >= cutoff]

    def _bucket(family: str):
        rs = [r for r in recent if _family(r) == family]
        used = sum(_counted(r, weights) for r in rs)
        resets_at = (rs[0].ts + ONE_WEEK) if rs else None
        return used, resets_at

    opus_used, opus_reset = _bucket("opus")
    sonnet_used = sum(_counted(r, weights)
                      for r in recent if _family(r) in ("sonnet", "haiku"))
    sonnet_src = [r for r in recent if _family(r) in ("sonnet", "haiku")]
    sonnet_reset = (sonnet_src[0].ts + ONE_WEEK) if sonnet_src else None

    week_opus = WindowSnapshot(
        used=opus_used,
        budget=max(budgets["week_opus"], observed["week_opus"], opus_used),
        resets_at=opus_reset,
        observed_max=observed["week_opus"],
    )
    week_sonnet = WindowSnapshot(
        used=sonnet_used,
        budget=max(budgets["week_sonnet"], observed["week_sonnet"], sonnet_used),
        resets_at=sonnet_reset,
        observed_max=observed["week_sonnet"],
    )
    return Snapshot(five_hour=five, week_opus=week_opus,
                    week_sonnet=week_sonnet, now=now)
```

- [ ] **Step 4: Run — expect pass**

Run: `pytest tests/test_aggregator.py -v`
Expected: all aggregator tests PASS (≥7 tests).

- [ ] **Step 5: Commit**

```bash
git add tokenfollow/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): weekly rolling split + model families + cache weight"
```

---

## Task 5: BudgetManager — load/create config, hybrid max, persist

**Files:**
- Create: `tokenfollow/budget.py`
- Create: `tests/test_budget.py`

- [ ] **Step 1: Write the first-run test**

```python
# tests/test_budget.py
from __future__ import annotations

import json
from pathlib import Path

from tokenfollow.budget import BudgetManager


def test_first_run_creates_config(tmp_path: Path):
    cfg = tmp_path / "config.json"
    assert not cfg.exists()
    bm = BudgetManager(cfg)
    assert cfg.exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["defaults"]["5h_tokens"] == 88_000_000
    assert data["weights"]["cache_read"] == 0.1
    assert data["observed_max"]["5h_tokens"] == 0
    assert bm.refresh_seconds == 10
```

- [ ] **Step 2: Write the corrupted-config test**

```python
# append to tests/test_budget.py
def test_corrupted_config_moves_to_bak(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    BudgetManager(cfg)
    assert (tmp_path / "config.json.bak").exists()
    # new one was created
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "defaults" in data
```

- [ ] **Step 3: Write the hybrid + bump + roundtrip tests**

```python
# append to tests/test_budget.py
from tokenfollow.aggregator import Snapshot, WindowSnapshot
from datetime import datetime, timezone


def _ws(used, budget, observed_max):
    return WindowSnapshot(used=used, budget=budget,
                          resets_at=None, observed_max=observed_max)


def _snap(five_used, opus_used, sonnet_used):
    return Snapshot(
        five_hour=_ws(five_used, 88_000_000, 0),
        week_opus=_ws(opus_used, 70_000_000, 0),
        week_sonnet=_ws(sonnet_used, 440_000_000, 0),
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
    )


def test_observed_bump_on_exceed(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    # Simulate current usage exceeding the default 5h budget
    snap = _snap(five_used=100_000_000, opus_used=0, sonnet_used=0)
    changed = bm.maybe_bump(snap)
    assert changed is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["observed_max"]["5h_tokens"] == 100_000_000


def test_observed_never_decreases(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    bm.maybe_bump(_snap(100_000_000, 0, 0))
    # Smaller snapshot should not shrink observed max.
    changed = bm.maybe_bump(_snap(50_000_000, 0, 0))
    assert changed is False
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["observed_max"]["5h_tokens"] == 100_000_000


def test_budgets_and_weights_exposed(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    assert bm.budgets == {"5h": 88_000_000,
                          "week_opus": 70_000_000,
                          "week_sonnet": 440_000_000}
    assert bm.observed == {"5h": 0, "week_opus": 0, "week_sonnet": 0}
    assert bm.weights == {"cache_read": 0.1}
```

- [ ] **Step 4: Run — expect failure**

Run: `pytest tests/test_budget.py -v`
Expected: ImportError for `tokenfollow.budget`.

- [ ] **Step 5: Implement `BudgetManager`**

```python
# tokenfollow/budget.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from tokenfollow.aggregator import Snapshot


DEFAULTS = {
    "weights": {"cache_read": 0.1},
    "defaults": {
        "5h_tokens": 88_000_000,
        "week_opus_tokens": 70_000_000,
        "week_sonnet_tokens": 440_000_000,
    },
    "observed_max": {
        "5h_tokens": 0,
        "week_opus_tokens": 0,
        "week_sonnet_tokens": 0,
    },
    "window": {"x": None, "y": None},
    "refresh_seconds": 10,
}


class BudgetManager:
    """Owns config.json. Exposes budgets, observed_max, weights, position."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data = self._load_or_init()

    # --- loading / saving -------------------------------------------------
    def _load_or_init(self) -> Dict:
        if not self._path.exists():
            data = _deepcopy(DEFAULTS)
            self._write(data)
            return data
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._path.replace(self._path.with_suffix(self._path.suffix + ".bak"))
            data = _deepcopy(DEFAULTS)
            self._write(data)
            return data
        # fill in any missing keys to survive partial configs
        return _merge_defaults(data, DEFAULTS)

    def _write(self, data: Dict) -> None:
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save(self) -> None:
        self._write(self._data)

    # --- exposed properties ----------------------------------------------
    @property
    def budgets(self) -> Dict[str, int]:
        d = self._data["defaults"]
        return {"5h": d["5h_tokens"],
                "week_opus": d["week_opus_tokens"],
                "week_sonnet": d["week_sonnet_tokens"]}

    @property
    def observed(self) -> Dict[str, int]:
        o = self._data["observed_max"]
        return {"5h": o["5h_tokens"],
                "week_opus": o["week_opus_tokens"],
                "week_sonnet": o["week_sonnet_tokens"]}

    @property
    def weights(self) -> Dict[str, float]:
        return dict(self._data["weights"])

    @property
    def refresh_seconds(self) -> int:
        return int(self._data["refresh_seconds"])

    @property
    def window_position(self):
        w = self._data["window"]
        return (w.get("x"), w.get("y"))

    def save_position(self, x: Optional[int], y: Optional[int]) -> None:
        self._data["window"]["x"] = x
        self._data["window"]["y"] = y
        self._write(self._data)

    # --- bumping ---------------------------------------------------------
    def maybe_bump(self, snap: Snapshot) -> bool:
        changed = False
        pairs = [
            ("5h_tokens", snap.five_hour.used),
            ("week_opus_tokens", snap.week_opus.used),
            ("week_sonnet_tokens", snap.week_sonnet.used),
        ]
        for key, used in pairs:
            if used > self._data["observed_max"][key]:
                self._data["observed_max"][key] = used
                changed = True
        if changed:
            self._write(self._data)
        return changed


def _deepcopy(obj):
    return json.loads(json.dumps(obj))


def _merge_defaults(data, defaults):
    if not isinstance(defaults, dict):
        return data if data is not None else defaults
    out = dict(defaults)
    if isinstance(data, dict):
        for k, v in defaults.items():
            if k in data:
                out[k] = _merge_defaults(data[k], v)
    return out
```

- [ ] **Step 6: Run — expect pass**

Run: `pytest tests/test_budget.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add tokenfollow/budget.py tests/test_budget.py
git commit -m "feat(budget): config persistence + hybrid max + observed bump"
```

---

## Task 6: BudgetManager — position save/load round-trip

**Files:**
- Modify: `tests/test_budget.py`

- [ ] **Step 1: Write the round-trip test**

```python
# append to tests/test_budget.py
def test_position_roundtrip(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm1 = BudgetManager(cfg)
    assert bm1.window_position == (None, None)
    bm1.save_position(1500, 40)
    bm2 = BudgetManager(cfg)
    assert bm2.window_position == (1500, 40)


def test_partial_config_merged_with_defaults(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"refresh_seconds": 5}), encoding="utf-8")
    bm = BudgetManager(cfg)
    assert bm.refresh_seconds == 5
    assert bm.budgets["5h"] == 88_000_000     # default filled in
```

- [ ] **Step 2: Run — expect pass (implementation already supports these)**

Run: `pytest tests/test_budget.py -v`
Expected: both new tests PASS (merge_defaults handles partial).

- [ ] **Step 3: Commit**

```bash
git add tests/test_budget.py
git commit -m "test(budget): position roundtrip + partial-config merge"
```

---

## Task 7: GPUMonitor — nvidia-smi path + source selection

**Files:**
- Create: `tokenfollow/gpu.py`
- Create: `tests/test_gpu.py`

- [ ] **Step 1: Write the source-selection tests**

```python
# tests/test_gpu.py
from __future__ import annotations

import subprocess
from unittest.mock import patch, MagicMock

from tokenfollow.gpu import GPUMonitor


def _ok(stdout: str):
    m = MagicMock()
    m.returncode = 0
    m.stdout = stdout
    return m


def _fail():
    return subprocess.CalledProcessError(1, cmd="x")


def test_picks_nvidia_when_available():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    assert gm.source == "nvidia-smi"


def test_falls_back_to_perfcounter_when_nvidia_missing():
    calls = []
    def fake_run(cmd, *a, **kw):
        calls.append(cmd)
        if "nvidia-smi" in (cmd[0] if isinstance(cmd, list) else cmd):
            raise FileNotFoundError
        return _ok("27\n")
    with patch("subprocess.run", side_effect=fake_run):
        gm = GPUMonitor()
    assert gm.source == "perfcounter"


def test_source_none_when_both_fail():
    def fake_run(cmd, *a, **kw):
        raise FileNotFoundError
    with patch("subprocess.run", side_effect=fake_run):
        gm = GPUMonitor()
    assert gm.source == "none"
    assert gm.read() is None
```

- [ ] **Step 2: Write the nvidia-smi parsing tests**

```python
# append to tests/test_gpu.py
def test_nvidia_parse_single_gpu():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("42\n")):
        assert gm.read() == 42


def test_nvidia_parse_multi_gpu_takes_max():
    with patch("subprocess.run", return_value=_ok("12\n88\n55\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("12\n88\n55\n")):
        assert gm.read() == 88


def test_nvidia_read_returns_none_on_garbled_output():
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("not a number\n")):
        assert gm.read() is None
```

- [ ] **Step 3: Run — expect failure**

Run: `pytest tests/test_gpu.py -v`
Expected: ImportError / FAIL.

- [ ] **Step 4: Implement `GPUMonitor` (nvidia path + source detection only)**

```python
# tokenfollow/gpu.py
from __future__ import annotations

import subprocess
from typing import Optional


NVIDIA_CMD = [
    "nvidia-smi",
    "--query-gpu=utilization.gpu",
    "--format=csv,noheader,nounits",
]

PERFCOUNTER_CMD = [
    "powershell", "-NoProfile", "-Command",
    "(Get-Counter '\\GPU Engine(*engtype_3D)\\Utilization Percentage')"
    ".CounterSamples | Measure-Object -Property CookedValue -Sum | "
    "Select -ExpandProperty Sum",
]

_TIMEOUT_S = 1.5


class GPUMonitor:
    def __init__(self) -> None:
        self._last_good: Optional[int] = None
        self.source = self._detect_source()

    # --- detection -------------------------------------------------------
    def _detect_source(self) -> str:
        if self._try(NVIDIA_CMD) is not None:
            return "nvidia-smi"
        if self._try(PERFCOUNTER_CMD) is not None:
            return "perfcounter"
        return "none"

    def _try(self, cmd) -> Optional[int]:
        try:
            cp = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=_TIMEOUT_S, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        if cp.returncode != 0:
            return None
        return self._parse(cp.stdout)

    @staticmethod
    def _parse(stdout: str) -> Optional[int]:
        vals = []
        for line in stdout.splitlines():
            line = line.strip().replace(",", ".")
            if not line:
                continue
            try:
                vals.append(float(line))
            except ValueError:
                return None
        if not vals:
            return None
        return int(round(max(0.0, min(100.0, max(vals)))))

    # --- public read -----------------------------------------------------
    def read(self) -> Optional[int]:
        if self.source == "none":
            return None
        cmd = NVIDIA_CMD if self.source == "nvidia-smi" else PERFCOUNTER_CMD
        val = self._try(cmd)
        if val is not None:
            self._last_good = val
            return val
        return self._last_good
```

- [ ] **Step 5: Run — expect pass**

Run: `pytest tests/test_gpu.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tokenfollow/gpu.py tests/test_gpu.py
git commit -m "feat(gpu): nvidia-smi reader with source auto-detection"
```

---

## Task 8: GPUMonitor — perfcounter fallback, clamp, timeout / last-good

**Files:**
- Modify: `tests/test_gpu.py`

- [ ] **Step 1: Write perfcounter + clamp + timeout tests**

```python
# append to tests/test_gpu.py
def test_perfcounter_clamp_upper():
    # multi-engine counter sums can exceed 100
    with patch("subprocess.run", side_effect=[FileNotFoundError, _ok("137.5\n")]):
        gm = GPUMonitor()
    assert gm.source == "perfcounter"
    with patch("subprocess.run", return_value=_ok("137.5\n")):
        assert gm.read() == 100


def test_perfcounter_clamp_lower():
    with patch("subprocess.run", side_effect=[FileNotFoundError, _ok("5\n")]):
        gm = GPUMonitor()
    with patch("subprocess.run", return_value=_ok("-3\n")):
        assert gm.read() == 0


def test_timeout_returns_last_good():
    # Detect succeeds once…
    with patch("subprocess.run", return_value=_ok("42\n")):
        gm = GPUMonitor()
    # …first read gives a good value
    with patch("subprocess.run", return_value=_ok("42\n")):
        assert gm.read() == 42
    # …second read times out, should return last good value
    with patch("subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1.5)):
        assert gm.read() == 42


def test_none_source_read_is_none():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        gm = GPUMonitor()
    assert gm.read() is None
```

- [ ] **Step 2: Run — expect pass (implementation already supports these)**

Run: `pytest tests/test_gpu.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_gpu.py
git commit -m "test(gpu): clamp + timeout + last-good coverage"
```

---

## Task 9: OverlayWindow — construct, render snapshot, color bands

**Files:**
- Create: `tokenfollow/ui.py`
- Create: `tests/test_ui_smoke.py`

- [ ] **Step 1: Write UI smoke tests (real Tk root, no mainloop)**

```python
# tests/test_ui_smoke.py
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta, timezone

import pytest

from tokenfollow.aggregator import Snapshot, WindowSnapshot
from tokenfollow.ui import OverlayWindow, band_color, BAND_GREEN, BAND_AMBER, BAND_RED


UTC = timezone.utc


def _snap(f=0.2, o=0.2, s=0.2, gpu=30):
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    return Snapshot(
        five_hour=WindowSnapshot(int(f * 88_000_000), 88_000_000,
                                 now + timedelta(hours=2, minutes=14), 0),
        week_opus=WindowSnapshot(int(o * 70_000_000), 70_000_000,
                                 now + timedelta(days=3, hours=5), 0),
        week_sonnet=WindowSnapshot(int(s * 440_000_000), 440_000_000,
                                   now + timedelta(days=4, hours=1), 0),
        now=now,
        gpu_percent=gpu,
    )


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no Tk display available: {e}")
    root.withdraw()
    yield root
    root.destroy()


def test_band_color_thresholds():
    assert band_color(0.50) == BAND_GREEN
    assert band_color(0.59) == BAND_GREEN
    assert band_color(0.60) == BAND_AMBER
    assert band_color(0.85) == BAND_AMBER
    assert band_color(0.86) == BAND_RED
    assert band_color(0.99) == BAND_RED


def test_window_constructs_and_renders(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap())
    tk_root.update_idletasks()
    text = w.label_texts()
    assert "5h" in text["five_hour"]
    assert "Opus" in text["week_opus"]
    assert "Sonnet" in text["week_sonnet"]
    assert "30" in text["gpu"]


def test_gpu_row_shows_na_when_none(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(gpu=None))
    assert "N/A" in w.label_texts()["gpu"]


def test_close_callback_fires(tk_root):
    called = []
    w = OverlayWindow(root=tk_root, on_close=lambda: called.append(True))
    w._on_close()
    assert called == [True]


def test_topmost_reasserted_on_restore(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    tk_root.attributes("-topmost", False)
    w._on_map(None)
    assert bool(tk_root.attributes("-topmost")) is True
```

- [ ] **Step 2: Run — expect failure**

Run: `pytest tests/test_ui_smoke.py -v`
Expected: ImportError for `tokenfollow.ui`.

- [ ] **Step 3: Implement `OverlayWindow`**

```python
# tokenfollow/ui.py
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from tokenfollow.aggregator import Snapshot, WindowSnapshot


BAND_GREEN = "#2e9e4b"
BAND_AMBER = "#d98e0b"
BAND_RED = "#c0392b"


def band_color(fraction: float) -> str:
    if fraction < 0.60:
        return BAND_GREEN
    if fraction <= 0.85:
        return BAND_AMBER
    return BAND_RED


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_delta(target: Optional[datetime], now: datetime) -> str:
    if target is None:
        return "idle"
    total = int((target - now).total_seconds())
    if total <= 0:
        return "resetting…"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {minutes}m"
    return f"resets in {minutes}m"


class OverlayWindow:
    """Four-row overlay: three token bars + GPU."""

    def __init__(self, *, root: Optional[tk.Tk] = None,
                 on_close: Callable[[], None]):
        self.root = root or tk.Tk()
        self.root.title("TokenFollow")
        self.root.geometry("320x180")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._on_close_cb = on_close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Map>", self._on_map)

        self._labels: Dict[str, tk.Label] = {}
        self._bars: Dict[str, ttk.Progressbar] = {}
        self._styles: Dict[str, str] = {}
        self._style = ttk.Style(self.root)

        for i, key in enumerate(("five_hour", "week_opus", "week_sonnet", "gpu")):
            lab = tk.Label(self.root, anchor="w", font=("Segoe UI", 9))
            lab.grid(row=i, column=0, sticky="ew", padx=6, pady=(4, 0))
            style_name = f"TokenFollow.{key}.Horizontal.TProgressbar"
            bar = ttk.Progressbar(self.root, length=300, mode="determinate",
                                  maximum=100, style=style_name)
            bar.grid(row=i, column=0, sticky="ew", padx=6, pady=(16, 4))
            self._labels[key] = lab
            self._bars[key] = bar
            self._styles[key] = style_name
        self.root.grid_columnconfigure(0, weight=1)

    # --- rendering -------------------------------------------------------
    def update(self, snap: Snapshot) -> None:
        self._render_token("five_hour", "5h window", snap.five_hour, snap.now)
        self._render_token("week_opus", "Week · Opus", snap.week_opus, snap.now)
        self._render_token("week_sonnet", "Week · Sonnet", snap.week_sonnet, snap.now)
        self._render_gpu(snap.gpu_percent)

    def _render_token(self, key: str, label: str,
                      w: WindowSnapshot, now: datetime) -> None:
        frac = (w.used / w.budget) if w.budget > 0 else 0.0
        frac = max(0.0, min(1.0, frac))
        color = band_color(frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = frac * 100
        self._labels[key]["text"] = (
            f"{label}   {_fmt_tokens(w.used)} / {_fmt_tokens(w.budget)}   ·   "
            f"{_fmt_delta(w.resets_at, now)}"
        )

    def _render_gpu(self, percent: Optional[int]) -> None:
        key = "gpu"
        if percent is None:
            self._bars[key]["value"] = 0
            self._style.configure(self._styles[key], background="#555",
                                  troughcolor="#222", bordercolor="#222")
            self._labels[key]["text"] = "GPU   N/A"
            return
        frac = max(0.0, min(1.0, percent / 100.0))
        color = band_color(frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = percent
        self._labels[key]["text"] = f"GPU   {percent} %"

    def label_texts(self) -> Dict[str, str]:
        return {k: lab["text"] for k, lab in self._labels.items()}

    # --- window lifecycle -----------------------------------------------
    def _on_map(self, _event) -> None:
        self.root.attributes("-topmost", True)

    def _on_close(self) -> None:
        try:
            self._on_close_cb()
        finally:
            self.root.destroy()

    def restore_position(self, pos) -> None:
        x, y = pos
        if x is not None and y is not None:
            self.root.geometry(f"+{int(x)}+{int(y)}")

    def current_position(self):
        # geometry is like "320x180+1500+40"
        geom = self.root.geometry()
        try:
            coords = geom.split("+")
            return int(coords[-2]), int(coords[-1])
        except (ValueError, IndexError):
            return None, None
```

- [ ] **Step 4: Run — expect pass**

Run: `pytest tests/test_ui_smoke.py -v`
Expected: all 5 UI tests PASS (skip gracefully only if no display is available, but on the user's Windows box they will run).

- [ ] **Step 5: Commit**

```bash
git add tokenfollow/ui.py tests/test_ui_smoke.py
git commit -m "feat(ui): overlay window with 4 rows, color bands, topmost"
```

---

## Task 10: Entry point + golden integration scenarios

**Files:**
- Create: `token_follow.py`
- Create: `tests/test_integration.py`
- Create: `tests/fixtures/fresh.jsonl`
- Create: `tests/fixtures/mid_window.jsonl`
- Create: `tests/fixtures/opus_near_cap.jsonl`
- Create: `tests/fixtures/after_idle.jsonl`

- [ ] **Step 1: Create fixture JSONL — `tests/fixtures/fresh.jsonl`**

One line, 6 minutes ago, tiny usage:

```
{"timestamp":"2026-04-21T11:54:00Z","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":1000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":200}}}
```

(The integration test will set `now = 2026-04-21T12:00:00Z`.)

- [ ] **Step 2: Create `tests/fixtures/mid_window.jsonl`**

Two hours of Opus usage starting 02:00 ago:

```
{"timestamp":"2026-04-21T10:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":500000,"cache_creation_input_tokens":1000000,"cache_read_input_tokens":2000000,"output_tokens":100000}}}
{"timestamp":"2026-04-21T11:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":500000,"cache_creation_input_tokens":1000000,"cache_read_input_tokens":2000000,"output_tokens":100000}}}
```

- [ ] **Step 3: Create `tests/fixtures/opus_near_cap.jsonl`**

Week of heavy Opus use, last message an hour ago:

```
{"timestamp":"2026-04-17T09:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":15000000,"cache_creation_input_tokens":5000000,"cache_read_input_tokens":10000000,"output_tokens":2000000}}}
{"timestamp":"2026-04-19T09:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":15000000,"cache_creation_input_tokens":5000000,"cache_read_input_tokens":10000000,"output_tokens":2000000}}}
{"timestamp":"2026-04-21T11:00:00Z","message":{"model":"claude-opus-4-7","usage":{"input_tokens":15000000,"cache_creation_input_tokens":5000000,"cache_read_input_tokens":10000000,"output_tokens":2000000}}}
```

- [ ] **Step 4: Create `tests/fixtures/after_idle.jsonl`**

Old activity, nothing in the current 5h:

```
{"timestamp":"2026-04-20T02:00:00Z","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":500,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":100}}}
```

- [ ] **Step 5: Write golden integration tests**

```python
# tests/test_integration.py
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.aggregator import aggregate
from tokenfollow.budget import BudgetManager
from tokenfollow.parser import UsageParser


UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures"


def _scenario(tmp_path, fixture_name, now):
    projects = tmp_path / "projects" / "FakeProject"
    projects.mkdir(parents=True)
    shutil.copy(FIXTURES / fixture_name, projects / fixture_name)
    parser = UsageParser(tmp_path / "projects")
    records = parser.scan()
    bm = BudgetManager(tmp_path / "config.json")
    snap = aggregate(records, bm.budgets, bm.observed, now, bm.weights)
    return snap


def test_golden_fresh(tmp_path: Path):
    snap = _scenario(tmp_path, "fresh.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    assert snap.five_hour.used == 1200      # 1000 input + 200 output
    assert snap.five_hour.resets_at is not None
    assert snap.week_opus.used == 0
    assert snap.week_sonnet.used == 1200


def test_golden_mid_window(tmp_path: Path):
    snap = _scenario(tmp_path, "mid_window.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    # per line: 500k + 1M + 2M*0.1 + 100k = 1_800_000; ×2 = 3_600_000
    assert snap.five_hour.used == 3_600_000
    assert snap.week_opus.used == 3_600_000


def test_golden_opus_near_cap(tmp_path: Path):
    snap = _scenario(tmp_path, "opus_near_cap.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    # per line: 15M + 5M + 10M*0.1 + 2M = 23_000_000; 3 lines in last 7d
    assert snap.week_opus.used == 69_000_000
    assert snap.week_opus.used < snap.week_opus.budget
    # The most recent record is within the last 5h.
    assert snap.five_hour.used == 23_000_000


def test_golden_after_idle(tmp_path: Path):
    snap = _scenario(tmp_path, "after_idle.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    assert snap.five_hour.used == 0
    assert snap.five_hour.resets_at is None
    assert snap.week_sonnet.used == 600
```

- [ ] **Step 6: Run — expect pass**

Run: `pytest tests/test_integration.py -v`
Expected: all 4 golden tests PASS.

- [ ] **Step 7: Write `token_follow.py` entry point**

```python
# token_follow.py
"""TokenFollow — always-on-top Claude Code usage + GPU overlay."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.aggregator import aggregate
from tokenfollow.budget import BudgetManager
from tokenfollow.gpu import GPUMonitor
from tokenfollow.parser import UsageParser
from tokenfollow.ui import OverlayWindow


HERE = Path(__file__).resolve().parent
CLAUDE_PROJECTS_ROOT = Path.home() / ".claude" / "projects"


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    bm = BudgetManager(HERE / "config.json")
    parser = UsageParser(CLAUDE_PROJECTS_ROOT)
    gpu = GPUMonitor()

    def on_close():
        x, y = win.current_position()
        bm.save_position(x, y)
        parser.save_cache(HERE / "cache.json")
        bm.save()

    win = OverlayWindow(on_close=on_close)
    win.restore_position(bm.window_position)

    def tick():
        try:
            records = parser.scan()
            snap = aggregate(records, bm.budgets, bm.observed,
                             datetime.now(tz=timezone.utc), bm.weights)
            snap.gpu_percent = gpu.read()
            bm.maybe_bump(snap)
            win.update(snap)
        except Exception:                     # pragma: no cover
            logging.exception("tick failed; keeping last snapshot")
        win.root.after(bm.refresh_seconds * 1000, tick)

    tick()
    win.root.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Commit**

```bash
git add token_follow.py tests/test_integration.py tests/fixtures/
git commit -m "feat: entry point + golden integration scenarios"
```

---

## Task 11: Feature matrix + enforcement script

**Files:**
- Create: `tests/FEATURE_MATRIX.md`
- Create: `scripts/check_matrix.py`

- [ ] **Step 1: Write `tests/FEATURE_MATRIX.md`**

```markdown
# TokenFollow Feature Matrix

Each row is a user-visible behavior backed by at least one pytest test.
`scripts/check_matrix.py` enforces that every test id listed here is
collected by pytest.

| #   | Feature                                        | Test id                                             |
|-----|------------------------------------------------|-----------------------------------------------------|
| F01 | Parse usage block from JSONL                   | tests/test_parser.py::test_parse_valid_line         |
| F02 | Skip malformed JSONL line                      | tests/test_parser.py::test_skip_malformed           |
| F03 | Incremental byte-offset re-read                | tests/test_parser.py::test_incremental_reread       |
| F04 | 5h window anchored after gap                   | tests/test_aggregator.py::test_window_anchor_after_gap |
| F05 | Weekly rolling 7-day cutoff                    | tests/test_aggregator.py::test_weekly_split_by_family |
| F06 | Model family classification                    | tests/test_aggregator.py::test_unknown_model_ignored_in_weekly |
| F07 | Cache-read weighting                           | tests/test_aggregator.py::test_cache_read_weight    |
| F08 | Hybrid budget (defaults + observed max)        | tests/test_budget.py::test_observed_bump_on_exceed  |
| F09 | Observed never decreases                       | tests/test_budget.py::test_observed_never_decreases |
| F10 | Config persistence round-trip                  | tests/test_budget.py::test_position_roundtrip       |
| F11 | 3-bar + GPU UI renders                         | tests/test_ui_smoke.py::test_window_constructs_and_renders |
| F12 | Color banding thresholds                       | tests/test_ui_smoke.py::test_band_color_thresholds  |
| F13 | Always-on-top preserved on restore             | tests/test_ui_smoke.py::test_topmost_reasserted_on_restore |
| F14 | GPU source auto-detection                      | tests/test_gpu.py::test_picks_nvidia_when_available |
| F15 | GPU perfcounter clamp                          | tests/test_gpu.py::test_perfcounter_clamp_upper     |
| F16 | GPU timeout → last-good                        | tests/test_gpu.py::test_timeout_returns_last_good   |
| F17 | GPU unavailable → N/A in UI                    | tests/test_ui_smoke.py::test_gpu_row_shows_na_when_none |
| F18 | End-to-end fresh account                       | tests/test_integration.py::test_golden_fresh        |
| F19 | End-to-end mid-5h window                       | tests/test_integration.py::test_golden_mid_window   |
| F20 | End-to-end Opus near weekly cap                | tests/test_integration.py::test_golden_opus_near_cap |
| F21 | End-to-end after idle (no active window)       | tests/test_integration.py::test_golden_after_idle   |
```

- [ ] **Step 2: Write `scripts/check_matrix.py`**

```python
# scripts/check_matrix.py
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
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=str(ROOT), capture_output=True, text=True, check=False,
    )
    if cp.returncode not in (0, 5):          # 5 = no tests collected, still ran
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        return cp.returncode

    collected = set(
        line.strip() for line in cp.stdout.splitlines() if "::" in line
    )
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
```

- [ ] **Step 3: Run the matrix check — expect pass**

Run: `python scripts/check_matrix.py`
Expected: `MATRIX: 21 feature rows, all collected.`

- [ ] **Step 4: Commit**

```bash
git add tests/FEATURE_MATRIX.md scripts/check_matrix.py
git commit -m "test: feature matrix + enforcement script"
```

---

## Task 12: Coverage pass — hit ≥97 %

**Files:**
- Modify: any test files that need extra cases

- [ ] **Step 1: Run full coverage**

Run: `python -m pytest --cov=tokenfollow --cov-branch --cov-report=term-missing tests/`

- [ ] **Step 2: Inspect `missing` columns**

For each file with <97 % coverage, add a targeted test. Typical culprits:
- `parser.py`: `_parse_ts` fallback branch → add a test that feeds a `+00:00` timestamp.
- `gpu.py`: `_parse` empty-string branch, `return None` on ValueError — both already covered by `test_nvidia_read_returns_none_on_garbled_output` and `test_source_none_when_both_fail`.
- `budget.py`: `_merge_defaults` non-dict branch → covered by `test_partial_config_merged_with_defaults`.

Add minimal tests for remaining gaps using `pragma: no cover` ONLY on truly defensive branches (e.g. the top-level `try/except` in `tick()`, already excluded).

- [ ] **Step 3: Rerun with fail-under**

Run: `python -m pytest --cov=tokenfollow --cov-branch --cov-fail-under=97 tests/`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: reach 97% line+branch coverage"
```

---

## Task 13: `run_tests.bat`, `TokenFollow.bat`, README

**Files:**
- Create: `run_tests.bat`
- Create: `TokenFollow.bat`
- Create: `README.md`

- [ ] **Step 1: Write `run_tests.bat`**

```bat
@echo off
pushd "%~dp0"
python -m pytest --cov=tokenfollow --cov-branch --cov-report=term-missing --cov-fail-under=97 tests/
if errorlevel 1 (
  echo QA FAILED: coverage or tests
  popd
  exit /b 1
)
python scripts\check_matrix.py
if errorlevel 1 (
  echo QA FAILED: feature matrix
  popd
  exit /b 1
)
echo QA PASSED
popd
```

- [ ] **Step 2: Write `TokenFollow.bat`**

```bat
@echo off
start "" pythonw "G:\GitWorkSpace\TokenFollow\token_follow.py"
```

- [ ] **Step 3: Write `README.md`**

```markdown
# TokenFollow

Always-on-top Windows overlay that shows your current Claude Code
token consumption and GPU utilization.

Four rows:

1. **5h window** — tokens used in the current 5-hour Claude session and
   when it resets.
2. **Week · Opus** — Opus tokens used in the last 7 days.
3. **Week · Sonnet** — Sonnet + Haiku tokens used in the last 7 days.
4. **GPU** — current GPU utilization (auto-detects `nvidia-smi`; falls
   back to Windows GPU performance counters for AMD/Intel).

## Run

```
python token_follow.py
```

or double-click `TokenFollow.bat`. To launch from the desktop, copy
`TokenFollow.bat` there or right-click → Send to → Desktop (create
shortcut).

## Tune

`config.json` is created on first run and is hand-editable. Raise the
default budgets if you want the bars to calibrate against a higher
estimate; the script also auto-bumps any observed maximum, so the bars
can never exceed 100 %.

## Tests

```
run_tests.bat
```

Requires the dev extras: `pip install pytest pytest-cov freezegun`.

## Files

- `token_follow.py` — entry point
- `tokenfollow/` — package (parser, aggregator, budget, gpu, ui)
- `config.json`, `cache.json` — auto-generated at runtime
- `tests/` — pytest suite, coverage ≥ 97 %
- `docs/superpowers/` — spec + plan
```

- [ ] **Step 4: Commit**

```bash
git add run_tests.bat TokenFollow.bat README.md
git commit -m "chore: launcher bats + readme"
```

---

## Self-review notes (addressed inline before saving)

1. **Spec coverage** — every section of the spec has at least one task:
   - §2 UI → Task 9
   - §3 Data source → Task 2
   - §4 Token formula → Task 4 (cache_read weight test)
   - §5 Aggregation (5h + weekly) → Tasks 3 and 4
   - §6 Hybrid budget → Task 5
   - §7.1–7.6 Components → Tasks 1–10
   - §7.4 GPU → Tasks 7, 8
   - §8 Files on disk → Tasks 0, 10, 13
   - §9 config.json → Task 5
   - §10 Error handling → exercised in Tasks 2 (malformed/truncation), 5 (corrupt config), 8 (GPU timeout)
   - §11 QA → Tasks 11, 12, 13
2. **Placeholders** — none ("TBD"/"TODO"/"similar to" absent).
3. **Type consistency** — `UsageRecord`, `WindowSnapshot`, `Snapshot`,
   `budgets`/`observed`/`weights` mapping shapes match across tasks.
   Field `gpu_percent` consistently `int | None`.
