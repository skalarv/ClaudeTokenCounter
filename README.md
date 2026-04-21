# TokenFollow

An always-on-top Windows overlay that shows your Claude Code token usage and
GPU utilisation in real time.  Four progress bars update every 10 seconds:
the current 5-hour session, weekly Opus usage, weekly Sonnet+Haiku usage, and
GPU load — each colour-coded green / amber / red as you approach your limits.

```
+------------------------------------------+
|  5h window   23.4M / 88.0M  · resets in 2h 14m  |
|  [==========================================>   ] |
|  Week · Opus  14.1M / 70.0M · resets in 4d 3h   |
|  [=========================                    ] |
|  Week · Sonnet 88.2M / 440M · resets in 4d 3h   |
|  [=========                                   ] |
|  GPU   47 %                                      |
|  [========================                     ] |
+------------------------------------------+
```

---

## Install

Full instructions: [docs/INSTALL.md](docs/INSTALL.md)

**One-step install:** double-click `install.bat`.

It checks Python 3.8+, verifies tkinter, installs test dependencies, and
creates a Desktop shortcut — all in one go.

---

## Use

Double-click the **TokenFollow** Desktop shortcut, or run:

```
python token_follow.py
```

Full usage guide (window rows, config keys, GPU source selection, resetting
budgets): [docs/USAGE.md](docs/USAGE.md)

---

## Architecture

JSONL logs flow from `~/.claude/projects/` through `UsageParser` →
`aggregate()` → `OverlayWindow`; `GPUMonitor` feeds GPU utilisation into the
same `Snapshot`.  The package is split into five focused modules so the 97%+
branch-coverage gate can be met with fast, isolated unit tests.

Full diagram and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

---

## Test

```
run_tests.bat
```

Runs pytest with coverage (≥ 97% required) then the bidirectional feature-
matrix check.  Requires `pip install pytest pytest-cov` (done automatically by
`install.bat`).

---

## Requirements

| Item | Minimum |
|---|---|
| OS | Windows 10 (1903+) / Windows 11 |
| Python | 3.8+ with `tkinter` (use the official [python.org](https://www.python.org/downloads/) installer) |
| Claude Code | Any version — `~/.claude/projects/` must exist |

---

## License

MIT — see [LICENSE](LICENSE).
