# TokenFollow — Always-On-Top Claude Code Usage Overlay

**Date:** 2026-04-21
**Status:** Approved design, ready for implementation planning
**Author:** Yaron Zvirin (with Claude)

## 1. Goal

Provide a small always-on-top desktop window that shows, at a glance, how
many tokens have been consumed in the current Claude Code usage windows
and how long until each window resets. Target plan: Claude Max 5x ($100).

The window refreshes every 10 seconds and is driven entirely by local
data — no network calls, no API keys.

## 2. What the user sees

Three stacked token bars with labels and countdown text, plus a fourth
line showing current GPU utilization. Approximate layout
(320 × 180 px, standard Windows title bar):

```
+------------------------------------------------------+
| TokenFollow                           _  [ ]   x     |
+------------------------------------------------------+
| 5h window     [#####.........]  12.3M / 88M          |
|                                    resets in 2h 14m  |
| Week · Opus   [#########.....]  58M / 70M            |
|                                    resets in 3d 5h   |
| Week · Sonnet [##............]  82M / 440M           |
|                                    resets in 4d 1h   |
| GPU           [####..........]  27 %                 |
+------------------------------------------------------+
```

Color bands on every bar (tokens and GPU):

| Fill % | Color  |
|--------|--------|
| < 60%  | green  |
| 60–85% | amber  |
| > 85%  | red    |

The GPU bar reuses the same color logic but represents current
utilization, not consumption against a quota — "red" just means the
GPU is busy, which is not necessarily bad.

Behaviors:
- Always-on-top (`attributes('-topmost', True)`), re-asserted after the
  user restores from minimize.
- Minimize and close via the native title bar buttons. Close persists
  window position and any bumped budgets.
- Draggable via the title bar (native behavior; no custom handler).
- On first launch, the window appears near the top-right of the primary
  display. Subsequent launches restore the last position.
- Refresh tick fires every 10 s via `root.after(10_000, tick)`. Minimize
  does not pause the tick; the data stays current for the next restore.

## 3. Data source

Claude Code writes one JSONL file per session under
`C:\Users\Yaron\.claude\projects\<slug>\<session-uuid>.jsonl`. Each
assistant message line includes a `usage` block, for example:

```json
"usage": {
  "input_tokens": 6,
  "cache_creation_input_tokens": 10708,
  "cache_read_input_tokens": 19477,
  "output_tokens": 247,
  "server_tool_use": { "web_search_requests": 0, "web_fetch_requests": 0 }
}
```

Each record we extract is a 6-tuple:

```
(timestamp_utc, model, input, cache_create, cache_read, output)
```

`timestamp_utc` is parsed from the message's `timestamp` field (ISO 8601
UTC). `model` is read from `message.model` and classified into one of
`opus`, `sonnet`, `haiku`, or `other` by prefix match.

The only other external path the application touches is read-only:
`C:\Users\Yaron\.claude\projects\` and its descendants.

## 4. Counted-token formula

Account-level limits weight cache-read tokens below fresh ones. The
default weighting (tunable in `config.json`):

```
counted = input_tokens
        + cache_creation_input_tokens
        + cache_read_input_tokens * weights.cache_read     # default 0.1
        + output_tokens
```

All other weights default to 1.0 and are not separately configurable in
v1.

## 5. Aggregation

### 5.1 Five-hour window

Anthropic anchors the 5 h window to the first message after an idle gap.
Algorithm:

1. Load every record from all projects, sort by `timestamp_utc`.
2. Walk forward. A record starts a new window when
   `record.ts - previous.ts >= 5h` (or it is the first record). The
   window's anchor is that record's timestamp.
3. The **current** window is the one whose `[anchor, anchor + 5h)`
   interval contains `now_utc`. If none does, no window is active and
   the bar shows "0 / budget · idle".
4. Totals: sum `counted` over all records in the current window.
5. Reset time: `anchor + 5h`. Displayed as `Xh Ym` countdown.

### 5.2 Weekly rolling

1. Cutoff: `now_utc - 7 days`.
2. Sum `counted` over all records with `timestamp_utc >= cutoff`, split
   by model family.
3. Opus weekly = sum of records whose family is `opus`.
4. Sonnet weekly = sum of records whose family is `sonnet` **or**
   `haiku` (Max limits pool them; haiku usage is negligible in
   practice).
5. Reset time for each weekly bar: `oldest_record_in_week.ts + 7 days`.
   If no records in the last 7 days, show the static budget with no
   countdown.

### 5.3 Timezone

All math is performed in UTC. Display-side countdowns are shown as
`Xh Ym` or `Xd Yh` deltas, which are timezone-agnostic. DST transitions
have no effect.

## 6. Budget hybrid

Three budgets — `5h`, `week_opus`, `week_sonnet` — follow the same
rule:

```
budget = max(defaults[key], observed_max[key])
```

- `defaults` ship with first-guess values for Max 5x and are
  user-editable in `config.json`:
  - `5h_tokens`: 88,000,000
  - `week_opus_tokens`: 70,000,000
  - `week_sonnet_tokens`: 440,000,000
- `observed_max` starts at 0 and is bumped whenever the **current**
  window's usage exceeds the stored max (on any tick, not just on
  window close). Once bumped, it never decreases. This guarantees the
  bar can never exceed 100%.
- Because the budget is always ≥ observed maximum, the bar can never
  exceed 100%.

Budgets are persisted to `config.json` on every tick that bumps a value,
and on clean exit.

## 7. Components (single package, split files for testability)

```
tokenfollow/
  __init__.py
  parser.py       UsageParser
  aggregator.py   Aggregator
  budget.py       BudgetManager
  gpu.py          GPUMonitor
  ui.py           OverlayWindow
```

`token_follow.py` at the repo root is the entry point: parses CLI args
(none in v1), constructs the four objects, starts the tkinter mainloop.

### 7.1 UsageParser (`parser.py`)

Responsibilities:

- Walk `~/.claude/projects/*/**/*.jsonl`.
- Maintain an **in-memory** byte-offset map per file:
  `{ path: {"offset": int, "size_at_last_scan": int} }`. On each scan
  within a session, resume reading from `offset`. If current file size
  < `offset` (rotation or truncation), restart that file from 0.
- For each new line, `json.loads` it; if `usage` missing or line
  malformed, skip silently (log to stderr only if a debug flag is set;
  v1 no flag).
- Also maintain an in-memory **records list** (the full history seen so
  far this session). On the first scan of a session, every JSONL is
  read from byte 0 and all records are loaded; on subsequent scans,
  only new bytes are read and their records appended.
- `cache.json` on disk is **not** used across runs in v1. A file with
  that name appears only because `save_cache()` is defined for future
  use; v1 writes it on clean exit for diagnostics but does not read it
  on startup. This keeps startup simple (always a full read) while the
  10-second loop stays cheap (incremental).

A full startup read of ~20 project directories with many sessions is
expected to complete in well under the 10 s tick budget on typical
hardware. If this becomes a problem in practice, persisting records
across runs is a straightforward follow-up.

Public API:

```python
class UsageParser:
    def __init__(self, projects_root: Path, cache_path: Path): ...
    def scan(self) -> list[UsageRecord]: ...
    def save_cache(self) -> None: ...
```

### 7.2 Aggregator (`aggregator.py`)

Pure functions operating on a list of `UsageRecord`:

```python
@dataclass
class WindowSnapshot:
    used: int
    budget: int
    resets_at: datetime | None    # None if no active window
    observed_max: int

@dataclass
class Snapshot:
    five_hour: WindowSnapshot
    week_opus: WindowSnapshot
    week_sonnet: WindowSnapshot
    now: datetime
    gpu_percent: int | None = None     # set by entry point after aggregate()

def aggregate(records: list[UsageRecord],
              budgets: Budgets,
              now: datetime,
              weights: Weights) -> Snapshot: ...
```

Supplying `now` as a parameter (rather than reading the clock inside)
makes every test deterministic.

### 7.3 BudgetManager (`budget.py`)

- Loads `config.json` at startup; creates one with defaults if missing
  or corrupted (corrupted → write `.bak` and start fresh).
- Exposes `budgets`, `weights`, `window_position`, `refresh_seconds`.
- `maybe_bump(snapshot) -> bool`: if any `snapshot.*.used > observed_max`,
  update and persist; return whether a write happened.
- `save_position(x, y)` and `save() -> None` for clean exit.

### 7.4 GPUMonitor (`gpu.py`)

Reads current GPU utilization as an integer 0–100. Source selection is
auto-detected once at startup and cached:

1. **NVIDIA path (preferred):** run `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits`
   and parse the first line. If multiple GPUs, report the max.
2. **Windows Performance Counter fallback (any GPU, incl. AMD/Intel):**
   shell out to
   `powershell -NoProfile -Command "(Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage').CounterSamples | Measure-Object -Property CookedValue -Sum | Select -ExpandProperty Sum"`
   and clamp to `[0, 100]`. The `engtype_3D` filter isolates graphics/compute
   engines and excludes idle video-decode counters.
3. **Unavailable:** return `None`; UI renders the GPU line as `N/A`.

Each call has a **1.5 s subprocess timeout**. A timeout or non-zero
exit is treated the same as "source unavailable for this tick" —
returns the last good value (or `None`) and keeps the app responsive.

Public API:

```python
class GPUMonitor:
    def __init__(self): ...             # detects source
    def read(self) -> int | None: ...   # 0..100 or None
    @property
    def source(self) -> str: ...        # "nvidia-smi" | "perfcounter" | "none"
```

No configuration in `config.json` for v1 — the auto-detect covers the
common Windows cases. If the user has multiple GPUs and wants a
specific one, that's a follow-up.

### 7.5 OverlayWindow (`ui.py`)

- Constructs a `tk.Tk()` root with `-topmost` = True.
- Three bars implemented with `ttk.Progressbar` + `tk.Label` rows, laid
  out with `grid`. Color is enforced via `ttk.Style` with a named style
  per band (`TokenFollow.Green.Horizontal.TProgressbar`, etc.).
- `update(snapshot: Snapshot)` updates each bar's value and label text
  (including the countdown).
- Binds `<Unmap>` / `<Map>` to re-assert `-topmost` on restore.
- On close (`WM_DELETE_WINDOW`), calls a user-provided callback so the
  entry point can `budget_manager.save()` before `root.destroy()`.

### 7.6 Entry point (`token_follow.py`)

```python
def main():
    budget_manager = BudgetManager(Path("config.json"))
    parser = UsageParser(CLAUDE_PROJECTS_ROOT, Path("cache.json"))
    gpu = GPUMonitor()
    window = OverlayWindow(
        on_close=lambda: (budget_manager.save(), parser.save_cache()),
    )
    window.restore_position(budget_manager.window_position)

    def tick():
        records = parser.scan()
        snap = aggregate(records, budget_manager.budgets,
                         datetime.now(tz=UTC), budget_manager.weights)
        snap.gpu_percent = gpu.read()          # int 0..100 or None
        budget_manager.maybe_bump(snap)
        window.update(snap)
        window.root.after(budget_manager.refresh_seconds * 1000, tick)

    tick()
    window.root.mainloop()
```

## 8. Files on disk

### 8.1 Shipped (version-controllable)

```
G:\GitWorkSpace\TokenFollow\token_follow.py
G:\GitWorkSpace\TokenFollow\tokenfollow\__init__.py
G:\GitWorkSpace\TokenFollow\tokenfollow\parser.py
G:\GitWorkSpace\TokenFollow\tokenfollow\aggregator.py
G:\GitWorkSpace\TokenFollow\tokenfollow\budget.py
G:\GitWorkSpace\TokenFollow\tokenfollow\gpu.py
G:\GitWorkSpace\TokenFollow\tokenfollow\ui.py
G:\GitWorkSpace\TokenFollow\TokenFollow.bat
G:\GitWorkSpace\TokenFollow\run_tests.bat
G:\GitWorkSpace\TokenFollow\pyproject.toml
G:\GitWorkSpace\TokenFollow\.coveragerc
G:\GitWorkSpace\TokenFollow\README.md
G:\GitWorkSpace\TokenFollow\scripts\check_matrix.py
G:\GitWorkSpace\TokenFollow\tests\__init__.py
G:\GitWorkSpace\TokenFollow\tests\conftest.py
G:\GitWorkSpace\TokenFollow\tests\FEATURE_MATRIX.md
G:\GitWorkSpace\TokenFollow\tests\fixtures\*.jsonl
G:\GitWorkSpace\TokenFollow\tests\test_parser.py
G:\GitWorkSpace\TokenFollow\tests\test_aggregator.py
G:\GitWorkSpace\TokenFollow\tests\test_budget.py
G:\GitWorkSpace\TokenFollow\tests\test_gpu.py
G:\GitWorkSpace\TokenFollow\tests\test_ui_smoke.py
G:\GitWorkSpace\TokenFollow\tests\test_integration.py
G:\GitWorkSpace\TokenFollow\docs\superpowers\specs\2026-04-21-tokenfollow-overlay-design.md
```

### 8.2 Auto-generated at runtime

```
G:\GitWorkSpace\TokenFollow\config.json
G:\GitWorkSpace\TokenFollow\cache.json
```

### 8.3 Read-only external input

```
C:\Users\Yaron\.claude\projects\*\*.jsonl
```

### 8.4 Launcher copy for desktop

`G:\GitWorkSpace\TokenFollow\TokenFollow.bat` is intended to be copied,
or shortcut-linked, to the user's Desktop:

```
C:\Users\Yaron\Desktop\TokenFollow.bat
```

Contents (absolute paths, so it works from any location):

```bat
@echo off
start "" pythonw "G:\GitWorkSpace\TokenFollow\token_follow.py"
```

## 9. Configuration file

`config.json` is created on first run and is hand-editable. The
application rewrites it whenever budgets bump, position changes, or on
clean exit.

```json
{
  "weights": { "cache_read": 0.1 },
  "defaults": {
    "5h_tokens": 88000000,
    "week_opus_tokens": 70000000,
    "week_sonnet_tokens": 440000000
  },
  "observed_max": {
    "5h_tokens": 0,
    "week_opus_tokens": 0,
    "week_sonnet_tokens": 0
  },
  "window": { "x": null, "y": null },
  "refresh_seconds": 10
}
```

If the file is missing, it is created with these values. If it is
malformed, the existing file is renamed to `config.json.bak` and a
fresh one is written.

## 10. Error handling

This is a passive overlay; it must never crash the user's session.

- Missing `~/.claude/projects/`: show "no data yet" placeholder labels,
  keep ticking.
- Malformed JSONL line: skip silently.
- File shrunk since last scan (rotation/truncation): reset offset to 0.
- `config.json` corruption: move to `.bak`, recreate fresh.
- GPU source unavailable (no `nvidia-smi`, no perfcounter, subprocess
  timeout, non-zero exit): `GPUMonitor.read()` returns `None`; UI
  shows `GPU N/A` with an empty bar. No crashes, no retries.
- Exception inside `tick()`: caught at the top of `tick()`; logged to
  stderr; window keeps last snapshot visible; next tick still
  scheduled.

No retries, no exponential backoff, no external logging framework. Stdlib
`logging` at WARNING level to stderr only.

## 11. QA

### 11.1 Targets

- **Syntax coverage (line + branch) ≥ 97 %** via `pytest-cov` with
  `branch = True`.
- **Functional coverage = 100 %** — every row in
  `tests/FEATURE_MATRIX.md` has at least one named pytest test, and a
  matrix-verification script fails the build if any row is missing its
  test or any test lacks a matrix row.

### 11.2 Tools

Runtime dependencies remain stdlib-only (`tkinter`, `json`, `pathlib`,
`datetime`, `logging`). Test-time only:

- `pytest`
- `pytest-cov`
- `freezegun` — deterministic `now_utc` in aggregator tests

### 11.3 `.coveragerc`

```ini
[run]
branch = True
source = tokenfollow

[report]
fail_under = 97
exclude_lines =
    pragma: no cover
    if __name__ == .__main__.:
```

### 11.4 Test modules

| File | Scope |
|------|-------|
| `test_parser.py` | Malformed lines; missing `usage`; unknown model; incremental re-read; new file mid-run; truncation/rotation; empty projects dir; multi-project; unicode in paths; ISO timestamp variants. |
| `test_aggregator.py` | Empty records; single record; 5h-gap boundaries (4h59m59s, exactly 5h, 5h1s); out-of-order input; future-dated record (clock skew); model-family classification for opus/sonnet/haiku/unknown; cache-read weight; 7d cutoff at exactly 7×24h; UTC correctness. |
| `test_budget.py` | First run (no config); corrupted config → `.bak` + regenerate; missing keys in config; hybrid `max(default, observed)`; observed bump when exceeded; no downward bump; round-trip persistence; position save/load with nulls. |
| `test_gpu.py` | Source auto-detection picks `nvidia-smi` when present; falls back to perfcounter when only that works; returns `None` when both fail; subprocess timeout yields last-good value; CSV parsing of `nvidia-smi` output (single GPU, multi-GPU takes max); clamps perfcounter sum to `[0, 100]`. All subprocess calls mocked with `unittest.mock.patch('subprocess.run')`. |
| `test_ui_smoke.py` | `OverlayWindow` constructs; `update(snap)` renders all four rows; GPU row shows `N/A` when `gpu_percent is None`; color bands at 58/72/90 %; minimize/restore preserves topmost; close callback invoked. Uses a real `Tk()` root but never calls `mainloop()`. |
| `test_integration.py` | Four golden scenarios (fresh account, mid-5h, Opus week near cap, after 6h idle). Fixture JSONL → full pipeline → assert rendered label strings char-for-char. |

### 11.5 Feature matrix

`tests/FEATURE_MATRIX.md` is checked into the repo:

| #   | Feature                                       | Test(s)                                           |
|-----|-----------------------------------------------|---------------------------------------------------|
| F01 | Parse usage block from JSONL                  | `test_parser::test_parse_valid_line`              |
| F02 | Skip malformed line                           | `test_parser::test_skip_malformed`                |
| F03 | Incremental byte-offset re-read               | `test_parser::test_incremental_reread`            |
| F04 | 5h window anchored to first-after-gap         | `test_aggregator::test_window_anchor_after_gap`   |
| F05 | Weekly rolling 7-day cutoff                   | `test_aggregator::test_weekly_cutoff`             |
| F06 | Opus/Sonnet/Haiku model classification        | `test_aggregator::test_model_family`              |
| F07 | Cache-read weighting                          | `test_aggregator::test_cache_read_weight`         |
| F08 | Hybrid budget (defaults + observed max)       | `test_budget::test_hybrid_max`                    |
| F09 | Observed budget auto-bump                     | `test_budget::test_observed_bump`                 |
| F10 | Config persistence round-trip                 | `test_budget::test_roundtrip`                     |
| F11 | 3-bar UI renders correct percentages          | `test_ui_smoke::test_render`                      |
| F12 | Color banding at thresholds                   | `test_ui_smoke::test_color_bands`                 |
| F13 | Always-on-top preserved after restore         | `test_ui_smoke::test_topmost_after_restore`       |
| F14 | Position remembered across runs               | `test_budget::test_position_roundtrip`            |
| F15 | End-to-end: fixtures → expected label text    | `test_integration::test_golden_*` (×4)            |
| F16 | GPU source auto-detection (nvidia → perf → none) | `test_gpu::test_source_selection`              |
| F17 | `nvidia-smi` parsing (single + multi-GPU max) | `test_gpu::test_nvidia_parse`                     |
| F18 | Perf-counter fallback + `[0,100]` clamp       | `test_gpu::test_perfcounter_clamp`                |
| F19 | Subprocess timeout returns last-good / `None` | `test_gpu::test_timeout`                          |
| F20 | UI renders GPU row and `N/A` when unavailable | `test_ui_smoke::test_gpu_row`                     |

### 11.6 Matrix enforcement — `scripts/check_matrix.py`

Parses `FEATURE_MATRIX.md`, collects pytest test ids via
`pytest --collect-only -q`, and asserts:

1. Every test id listed in the matrix is actually collected.
2. Every collected test id appears in at least one matrix row, **or** is
   explicitly marked with `@pytest.mark.matrix_exempt`.

Non-zero exit code on any mismatch.

### 11.7 `run_tests.bat`

```bat
@echo off
pushd "%~dp0"
python -m pytest --cov=tokenfollow --cov-branch --cov-report=term-missing --cov-fail-under=97 tests/
if errorlevel 1 ( echo QA FAILED & popd & exit /b 1 )
python scripts\check_matrix.py
if errorlevel 1 ( echo MATRIX FAILED & popd & exit /b 1 )
echo QA PASSED
popd
```

## 12. Non-goals (v1)

- Per-project breakdowns.
- Historical charts or sparklines.
- Cost display in dollars.
- Cross-platform packaging (macOS / Linux) — the design should not
  Windows-lock the Python code, but no testing happens outside Windows
  in v1.
- Auto-update of the script itself.
- System-tray icon.

## 13. Open risks / known unknowns

- **Budget defaults are estimates.** The hybrid auto-bump compensates,
  but until the user hits a real limit at least once, the percentages
  are best-guess.
- **Weekly reset semantics.** Anthropic's exact weekly reset policy is
  not publicly documented as rolling-7d; it may be a calendar week or
  billing-cycle-aligned. v1 implements rolling-7d; if experience shows
  this drifts, a `weekly_mode: "rolling" | "calendar"` config key is a
  trivial follow-up.
- **Cache-read weight of 0.1** is a community estimate. Real weighting
  may differ; tunable in `config.json`.
