# TokenFollow — Usage Guide

## Launching

**From the Desktop:** double-click the `TokenFollow` shortcut (created by
`install.bat`).

**From a terminal:**

```
python token_follow.py
```

**Without a console window:**

```
TokenFollow.bat
```

The `.bat` calls `pythonw` so no console window appears.

---

## What the four rows mean

```
+----------------------------------------------+
|  5h window    23.4M / 88.0M   ·   resets in 2h 14m  |
|  [=========================================>      ]   |
|  Week · Opus  14.1M / 70.0M   ·   resets in 4d 3h   |
|  [========================                    ]       |
|  Week · Sonnet 88.2M / 440.0M ·   resets in 4d 3h   |
|  [========                                    ]       |
|  GPU   47 %                                          |
|  [========================                    ]       |
+----------------------------------------------+
```

### Row 1 — 5h window

Shows token usage within the current 5-hour Claude Code session and the time
remaining until it resets.

**How the 5-hour anchor works:**

* Claude Code sessions are identified by gaps in the JSONL timestamps.
* When a new message arrives after a gap of **5 hours or more**, a new window
  begins — the timestamp of that first message becomes the **anchor**.
* The window ends at `anchor + 5h`; at that point the bar resets if a new
  session starts.
* If you have been idle for more than 5 hours, the bar shows `idle` rather
  than a countdown.

### Row 2 — Week · Opus

Total weighted tokens from all `claude-opus-*` model turns in the **rolling
7-day window** (`now − 7 days`).

The reset time shown is `oldest_opus_record_in_window + 7 days` — i.e., when
the oldest record will fall out of the 7-day window.

### Row 3 — Week · Sonnet

Total weighted tokens from `claude-sonnet-*` **and** `claude-haiku-*` turns in
the rolling 7-day window.  Haiku is grouped with Sonnet because they share the
same weekly token pool.

The reset time is `oldest_sonnet_or_haiku_record + 7 days`.

> **Note:** The 7-day window is a rolling count based on wall-clock time.
> Anthropic's actual billing period may reset on a fixed calendar date; the two
> will drift slightly at billing boundaries.

### Row 4 — GPU

Current GPU utilisation (0–100 %).  Source is selected at startup:

1. **nvidia-smi** — queried if found on PATH.
2. **Windows GPU performance counters** — PowerShell `Get-Counter` fallback,
   works for AMD / Intel discrete and integrated GPUs.
3. **N/A** — shown when neither source is available (no GPU, inaccessible
   counters, or a locked-down environment).

---

## Color bands

| Color | Range | Meaning |
|---|---|---|
| Green | < 60 % | Comfortable headroom |
| Amber | 60 % – 85 % | Approaching limit |
| Red | > 85 % | Near or at limit |

---

## Hybrid budget — why the bar never exceeds 100 %

Each window's budget is the **maximum** of three values:

```
budget = max(defaults.<window>_tokens, observed_max.<window>_tokens, current_used)
```

* `defaults.*` — your hand-set starting ceilings in `config.json`.
* `observed_max.*` — the highest usage ever seen by TokenFollow (auto-learned,
  persisted in `config.json`).
* `current_used` — the live value just computed.

Because `budget >= used` by construction, the fill fraction is always in
`[0, 1]` and the progress bar can never overflow.

---

## Tuning `config.json`

`config.json` is created next to `token_follow.py` on first run.  Edit it with
any text editor while the overlay is **closed** (or re-open after editing).

```jsonc
{
  "weights": {
    "cache_read": 0.1       // Community estimate: cache-read tokens count as 10 %
  },
  "defaults": {
    "5h_tokens": 88000000,          // Starting ceiling for the 5h window
    "week_opus_tokens": 70000000,   // Starting ceiling for weekly Opus
    "week_sonnet_tokens": 440000000 // Starting ceiling for weekly Sonnet+Haiku
  },
  "observed_max": {
    "5h_tokens": 0,          // Auto-learned; set to 0 to reset
    "week_opus_tokens": 0,
    "week_sonnet_tokens": 0
  },
  "window": {
    "x": null,   // Saved on close; set to null to reset position
    "y": null
  },
  "refresh_seconds": 10   // How often the overlay polls for new data
}
```

### Key-by-key reference

| Key | Default | Effect |
|---|---|---|
| `weights.cache_read` | `0.1` | Multiplier applied to `cache_read_input_tokens`; the community estimate is 0.1 (10 % of normal input cost) |
| `defaults.5h_tokens` | `88000000` | Starting budget for the 5-hour window; raise this if your usage regularly exceeds 88 M |
| `defaults.week_opus_tokens` | `70000000` | Starting weekly Opus budget |
| `defaults.week_sonnet_tokens` | `440000000` | Starting weekly Sonnet+Haiku budget |
| `observed_max.5h_tokens` | `0` | Auto-bumped whenever usage exceeds the stored value; set to `0` to forget the learned ceiling |
| `observed_max.week_opus_tokens` | `0` | Same, for weekly Opus |
| `observed_max.week_sonnet_tokens` | `0` | Same, for weekly Sonnet |
| `window.x` / `window.y` | `null` | Screen position persisted on close; delete or set to `null` to reset to default |
| `refresh_seconds` | `10` | Polling interval in seconds; lower values increase responsiveness but slightly increase CPU usage |

---

## Resetting budgets

To start fresh with default settings, delete (or rename) `config.json`:

```
del config.json
```

On the next launch a new `config.json` is created from defaults.  If you only
want to reset the auto-learned ceilings, zero out the `observed_max` section:

```jsonc
"observed_max": {
  "5h_tokens": 0,
  "week_opus_tokens": 0,
  "week_sonnet_tokens": 0
}
```

---

## GPU source selection

At startup `GPUMonitor` probes sources in order:

1. Runs `nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits`.
   If this succeeds and returns a number, `source` is set to `"nvidia-smi"`.
2. Runs a PowerShell `Get-Counter` query for `GPU Engine(*engtype_3D)\Utilization Percentage`.
   If this succeeds, `source` is set to `"perfcounter"`.
3. If both fail, `source` is `"none"` and the GPU row always shows `N/A`.

On transient failures after an initial success, the last-good value is
displayed rather than switching to `N/A`.

---

## Known limits

* **Rolling 7-day window vs. billing reset** — Anthropic bills on a fixed
  monthly or weekly boundary; the rolling-7-day count here may differ slightly
  at the billing boundary.
* **Windows-only GPU fallback** — the `perfcounter` path uses Windows-specific
  performance counter names; it will not work on macOS or Linux.
* **Per-project breakdowns** — not supported; all projects are summed together.
* **Dollar cost display** — not shown; token counts only.
* **sparklines / history graphs** — not implemented.
* **Auto-update** — there is no self-update mechanism; pull the repo to update.
* **System tray icon** — not implemented; the overlay is always a visible window.
