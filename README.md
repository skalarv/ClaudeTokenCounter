# TokenFollow

An always-on-top Windows overlay that shows your Claude Code usage and GPU
utilisation in real time.  Ten progress bars update every 10 seconds: the
current 5-hour session, your account's weekly all-models limit, weekly
Fable/Mythos, Opus, and Sonnet+Haiku usage, burn-rate projections for Fable
and Opus (5-hour and weekly), and GPU load — each colour-coded
green / amber / red as you approach your limits.

**Account sync:** where possible, bars show the *real* percentages from
Anthropic's account usage endpoint (the same source as Claude Code's
`/usage` panel), polled once a minute using your local Claude Code OAuth
credentials.  Local token estimates from the JSONL logs stay as annotations
and power the per-family breakdown and burn-rate projections.

```
+---------------------------------------------------+
|  5h window     36% · est 5.8M · resets in 3h 54m  |
|  [=================>                            ] |
|  Fable · 5h    proj 31.0M / 35.0M @ reset         |
|  [========================================>     ] |
|  Opus · 5h     idle                               |
|  [                                              ] |
|  Week · All    58% · resets in 23h 34m            |
|  [============================>                 ] |
|  Week · Fable  98% · est 85.4M · resets in 23h    |
|  [===============================================] |
|  Fable · week  overrun by 3.1M · resets in 23h    |
|  [===============================================] |
|  Week · Opus   30.5M / 369.3M · resets in 3h 5m   |
|  [====>                                         ] |
|  Opus · week   proj 30.5M / 369.3M @ reset        |
|  [====>                                         ] |
|  Week · Sonnet 25.2M / 440M   · resets in 4d 0h   |
|  [===>                                          ] |
|  GPU   47 %                                       |
|  [=======================>                      ] |
+---------------------------------------------------+
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
`aggregate()` → `OverlayWindow`; `GPUMonitor` feeds GPU utilisation and
`AccountUsageMonitor` feeds real account percentages (from the OAuth `/usage`
endpoint) into the same `Snapshot`.  Token usage is split by model family —
Fable/Mythos, Opus, and Sonnet+Haiku — with burn-rate projections for the
premium families.  The package is split into six focused modules so the 97%+
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
