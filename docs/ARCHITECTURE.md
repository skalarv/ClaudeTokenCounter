# TokenFollow — Architecture

## High-level data flow

```
~/.claude/projects/**/*.jsonl
          |
          v
    UsageParser.scan()
     (incremental byte-offset read)
          |
          v  List[UsageRecord]
          |
          +---------------------------+
          |                           |
          v                           v
    BudgetManager               GPUMonitor.read()
    .budgets / .observed              |
    .weights                          |  Optional[int]
          |                           |
          v                           |
     aggregate(records,               |
               budgets,               |
               observed,              |
               now,                   |
               weights,               |
               rate_windows)          |
          |                           |
          v  Snapshot                 |
          |                           |
          +-- snap.gpu_percent <------+
          |
          +-- snap.account <--- AccountUsageMonitor.read()
          |                     (OAuth /usage endpoint, background
          |                      thread, 60s cache, last-good)
          v
    BudgetManager.maybe_bump(snap)
    (updates observed_max in config.json if needed)
          |
          v
    OverlayWindow.update(snap)
    (redraws ten rows via tkinter)
          |
          v
    win.root.after(refresh_seconds * 1000, tick)
    (schedules next tick)
```

---

## Module responsibilities

### `tokenfollow/parser.py`

`UsageParser` owns the incremental JSONL reader.  On each `scan()` call it
walks every `*.jsonl` file under the configured `projects_root`, reads only
the bytes past the stored per-file offset, and appends new `UsageRecord`
objects to an in-memory list.  If a file shrinks between calls (log rotation),
the offset is reset to zero.  The accumulated record list is returned sorted
by timestamp.

The module-level `parse_line()` function handles a single raw JSON string: it
validates the presence of `usage`, `timestamp`, and `model` fields; normalises
the timestamp to UTC; and returns a frozen `UsageRecord` dataclass or `None`
for malformed input.  Malformed lines are silently skipped — the overlay never
crashes on bad data.

### `tokenfollow/aggregator.py`

`aggregate()` is a **pure function**: it takes the full record list, budget
mappings, and `now` as explicit parameters and returns a `Snapshot`.  Passing
`now` explicitly (rather than calling `datetime.now()` internally) makes every
test fully deterministic without any mocking.

Internally it identifies the current 5-hour window by grouping the sorted
record list into windows **anchored at their first record**: the first record
at or past `anchor + 5h` starts the next window (a window never stretches past
five hours, matching Claude's session semantics), then it selects the window
whose anchor satisfies `anchor <= now < anchor + 5h`.  The weekly windows are
computed by filtering to the 7-day rolling cutoff and splitting by model
family (`fable/mythos` vs `opus` vs `sonnet/haiku`).

For each premium family (Fable, Opus), `_family_windows()` builds the weekly
`WindowSnapshot` plus two `ProjectionSnapshot`s (5-hour and weekly): a
trailing-window burn rate (`projection.*_rate_window_s` seconds, clamped to
the in-window elapsed time) is extrapolated to the window's end.  The
projection budget is deliberately **not** inflated by the projected value, so
the UI can honestly show an overrun.

The hybrid budget formula — `max(default, observed_max, current_used)` —
ensures the progress-bar fill fraction is always in `[0, 1]`.

### `tokenfollow/budget.py`

`BudgetManager` is the single owner of `config.json`.  It loads the file at
construction (creating it from `DEFAULTS` if absent, or recovering from a
`.bak` if corrupted), merges any missing keys from `DEFAULTS` so old configs
remain forward-compatible, and exposes budget / weight / position data as
typed properties.

`maybe_bump()` is called after every aggregation cycle: it compares each
window's `used` value against the stored `observed_max` and writes an updated
`config.json` if any value has grown.  The file is written only when something
changes, minimising I/O.

### `tokenfollow/account.py`

`AccountUsageMonitor` polls Anthropic's OAuth usage endpoint — the source
behind Claude Code's `/usage` panel — for the account's real limit
percentages and reset times.  The access token is read fresh from
`~/.claude/.credentials.json` on every fetch (Claude Code refreshes that file
itself), travels to the subprocess via an **environment variable** (never
argv), and the HTTPS call is made through PowerShell so certificate
validation uses the Windows trust store — this survives TLS-intercepting
corporate proxies whose CA Python's bundled OpenSSL rejects.

Fetches run on a daemon thread and are rate-limited by
`account.refresh_seconds` (default 60 s); `read()` never blocks the Tk main
loop and returns the last-good `AccountUsage` during in-flight fetches or
after transient failures.  `parse_usage_payload()` treats the endpoint's
`limits` array as authoritative (kinds: `session`, `weekly_all`,
`weekly_scoped` with a per-model scope) and falls back to the legacy
`five_hour` / `seven_day` fields.

### `tokenfollow/gpu.py`

`GPUMonitor` probes available GPU sources once at construction time (via
`_detect_source`) and stores the result in `source`.  This avoids repeated
subprocess spawns during the startup tick.

At each `read()` call the appropriate command is run with a 1.5-second timeout.
If the subprocess fails transiently (timeout, non-zero exit, garbled output)
but a previous reading succeeded, the last-good integer is returned.  This
prevents the GPU row from flickering to `N/A` on momentary probe failures.

Multi-GPU nvidia-smi output (one number per line) is handled by taking the
maximum.  Values are clamped to `[0, 100]` to guard against any out-of-range
driver output.

### `tokenfollow/ui.py`

`OverlayWindow` owns all Tk state: the root window, progress bars, labels, and
custom ttk styles.  It uses `attributes("-topmost", True)` to stay above other
windows and reasserts that attribute on the `<Map>` event to survive workspace
switches.

Three pure helpers are kept separate from the class for testability:
* `band_color(fraction)` — colour threshold logic (no Tk dependency).
* `_fmt_tokens(n)` — compact number formatter.
* `_fmt_delta(target, now)` — countdown formatter.

The `on_close` callback pattern (passed at construction, called before
`root.destroy()`) allows the entry point to persist state without the UI
module depending on BudgetManager or UsageParser.

---

## Key design decisions

### Single-package layout vs. single-file

The code is split into a six-module `tokenfollow/` package rather than a
single `token_follow.py` because isolated modules make it possible to reach
97%+ branch coverage with fast, focused unit tests.  Each module has no runtime
side-effects on import; test files can import them without a Tk display or
a real `~/.claude` directory.

### Pure `aggregate()` function

`aggregate()` takes `now` as an explicit `datetime` parameter instead of
calling `datetime.now()` internally.  This is the single most important
testability decision: every aggregation test runs deterministically at any
virtual timestamp without patching or monkeypatching.

### Hybrid budget (max of default / observed / used)

Using `max(default, observed_max, current_used)` as the denominator prevents
the progress bar from ever exceeding 100%.  If a user's actual usage is larger
than any configured ceiling, the bar reaches exactly 100% and does not overflow.
`observed_max` auto-grows so the ceiling self-calibrates over time; users who
want to reset it can zero it in `config.json`.

### In-memory byte-offset cache

File offsets are held in the `UsageParser` instance for the lifetime of the
process.  On first scan every file is read from byte 0; subsequent scans read
only the new tail bytes.  This keeps the per-tick I/O proportional to new data
rather than total history size.  `save_cache()` writes the offsets to
`cache.json` on close — this file is purely diagnostic and is **not** loaded on
startup, so there is no risk of stale offsets causing missed records.

### UI decomposition

`band_color`, `_fmt_tokens`, and `_fmt_delta` are pure functions outside the
`OverlayWindow` class.  This lets the test suite verify their logic (including
every branch) in unit tests that run without a Tk display, while
`test_ui_smoke.py` covers the full window lifecycle in integration-style tests.

---

## Testing strategy

| Layer | Files | What is tested |
|---|---|---|
| **Unit — parser** | `tests/test_parser.py` | `parse_line`, `UsageParser.scan`, offset tracking, truncation recovery, `save_cache` |
| **Unit — aggregator** | `tests/test_aggregator.py` | 5h window anchoring, gap detection, weekly split (incl. Fable/Mythos), cache-read weighting, model-family mapping, burn-rate projections |
| **Unit — budget** | `tests/test_budget.py` | First-run creation, corrupt recovery, hybrid bump, position round-trip, partial-config merge |
| **Unit — gpu** | `tests/test_gpu.py` | Source detection, parse, clamp, last-good fallback, timeout behaviour |
| **Unit — account** | `tests/test_account.py` | Token extraction, `/usage` payload parsing, fetch caching, in-flight dedup, last-good fallback, env-var token transport |
| **Smoke — ui** | `tests/test_ui_smoke.py` | Full `OverlayWindow` lifecycle, all `band_color` / `_fmt_*` branches, position restore/read |
| **Golden integration** | `tests/test_integration.py` | Five canned JSONL fixtures → `aggregate()` → exact `Snapshot` field assertions |
| **Bidirectional matrix** | `scripts/check_matrix.py` + `tests/FEATURE_MATRIX.md` | Every test in pytest is listed in the matrix; every matrix row maps to a collected test |

Coverage gate: 97% branch coverage required; current coverage is 100%.

---

## Error-handling philosophy

* **Never crash the overlay.** The `tick()` function in `token_follow.py`
  wraps the entire aggregation pipeline in `try/except Exception` and logs the
  traceback at WARNING level.  The next tick is always scheduled regardless of
  failure.
* **Malformed data is skipped silently.** `parse_line()` returns `None` on any
  `json.JSONDecodeError`, missing fields, or unparseable timestamp; bad lines
  are counted as absent rather than raised.
* **Subprocess failures degrade gracefully.** `GPUMonitor._try()` catches
  `FileNotFoundError`, `TimeoutExpired`, and `OSError`; non-zero exit codes
  are also treated as failures.  The last-good GPU value is preserved across
  transient failures.
* **Config corruption is recovered automatically.** If `config.json` cannot be
  parsed, it is renamed to `config.json.bak` and a fresh default file is
  written; the user's data is preserved in the backup.

---

## Known non-goals

The following features are explicitly out of scope (per the original design
spec):

* Per-project token breakdowns
* Sparklines or usage history graphs
* Dollar-cost display
* macOS / Linux native GPU support (the perfcounter fallback is Windows-only)
* System tray icon (the overlay is always a visible window)
* Auto-update / self-patching mechanism
* Claude API calls from the overlay itself
