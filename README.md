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
- `tests/` — pytest suite, coverage = 100 %
- `docs/superpowers/` — spec + plan
