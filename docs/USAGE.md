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

## Account sync — why the bars match `/usage`

TokenFollow polls Anthropic's account usage endpoint — the same source that
Claude Code's `/usage` panel renders — once a minute, using the OAuth token
Claude Code stores in `~/.claude/.credentials.json` (read-only; TokenFollow
never modifies or transmits your credentials anywhere except to
`api.anthropic.com`).  Where the account reports a limit, the bar shows the
**real percentage and reset time** from your account; the local token count
parsed from the JSONL logs is kept as an `est …` annotation.

* **5h window** — driven by the account's `session` limit.
* **Week · All** — the account's weekly all-models limit (no local analogue).
* **Week · Fable / Opus / Sonnet** — driven by the account's per-model scoped
  limit when one is reported; otherwise these fall back to the local estimate
  (`used / budget` format).
* When the account marks a limit **critical**, the bar is forced red
  regardless of the percentage.
* If the endpoint is unreachable (offline, expired token), the last-good
  account value is kept; before the first success the bars simply show the
  local estimates and `Week · All` shows `N/A`.  The fetch runs on a
  background thread — the overlay never freezes waiting for the network.
* The HTTPS call is made through PowerShell so certificate validation uses
  the **Windows trust store**, which keeps the sync working behind
  TLS-intercepting corporate proxies.
* Disable with `"account": {"enabled": false}` in `config.json`.

Note the local per-family weekly rows can differ from your account numbers:
the logs only cover Claude Code on this machine, while your account also
counts claude.ai web/mobile chats, other machines, and cloud-side agent runs.
That is exactly why the account values are shown where available.

---

## What the ten rows mean

```
+------------------------------------------------------+
|  5h window     36% · est 5.8M  ·  resets in 3h 54m    |
|  [=================>                              ]   |
|  Fable · 5h    proj 31.0M / 35.0M @ reset             |
|  [=========================================>      ]   |
|  Opus · 5h     idle                                   |
|  [                                                ]   |
|  Week · All    58%             ·  resets in 23h 34m   |
|  [============================>                   ]   |
|  Week · Fable  98% · est 85.4M ·  resets in 23h 34m   |
|  [================================================]   |
|  Fable · week  overrun by 3.1M ·  resets in 23h 34m   |
|  [================================================]   |
|  Week · Opus   30.5M / 369.3M  ·  resets in 3h 5m     |
|  [====>                                           ]   |
|  Opus · week   proj 30.5M / 369.3M @ reset            |
|  [====>                                           ]   |
|  Week · Sonnet 25.2M / 440.0M  ·  resets in 4d 0h     |
|  [===>                                            ]   |
|  GPU   47 %                                           |
|  [=======================>                        ]   |
+------------------------------------------------------+
```

Rows showing a percentage (`36%`, `58%`, `98%`) are **account-synced** — real
values from Anthropic's usage endpoint.  Rows showing `used / budget` token
counts are local estimates from the JSONL logs.

### Row 1 — 5h window

Shows token usage (all model families combined) within the current 5-hour
Claude Code session and the time remaining until it resets.

**How the 5-hour anchor works:**

* A window is **anchored at its first message** and lasts exactly five hours.
* The first message at or after `anchor + 5h` starts a new window — even when
  you have been working continuously the whole time.  A window never
  stretches past five hours.
* If you have been idle past the end of the current window, the bar shows
  `idle` rather than a countdown.

### Rows 2–3 — Fable · 5h and Opus · 5h (burn-rate projections)

For each premium family (Fable, Opus) the overlay projects where usage will
land **at the end of the current 5-hour window** if you keep burning tokens at
the recent rate:

* The rate is measured over a trailing window (default 15 minutes,
  configurable via `projection.*_5h_rate_window_s`).
* `proj X / Y @ reset` — projected usage vs. budget at window end.
* `overrun by X` — the projection exceeds the budget; the bar pins at 100 %.
* `idle` — no active 5-hour window.

### Row 4 — Week · All (account only)

Your account's weekly all-models limit, straight from the usage endpoint.
There is no local-log analogue for this row; it shows `N/A` until the first
successful account fetch.

### Row 5 — Week · Fable

Total weighted tokens from `claude-fable-*` / `claude-mythos-*` turns in the
**rolling 7-day window** (`now − 7 days`).  The reset time shown is
`oldest_fable_record_in_window + 7 days` — when the oldest record falls out of
the 7-day window.

### Row 6 — Fable · week (burn-rate projection)

Same projection as the 5-hour rows, but for the weekly Fable window; the rate
is measured over a trailing 6 hours by default
(`projection.fable_week_rate_window_s`).

### Row 7 — Week · Opus

Total weighted tokens from all `claude-opus-*` model turns in the rolling
7-day window.

### Row 8 — Opus · week (burn-rate projection)

Weekly burn-rate projection for Opus, trailing 6 hours by default
(`projection.opus_week_rate_window_s`).

### Row 9 — Week · Sonnet

Total weighted tokens from `claude-sonnet-*` **and** `claude-haiku-*` turns in
the rolling 7-day window.  Haiku is grouped with Sonnet because they share the
same weekly token pool.

> **Note:** The 7-day windows are rolling counts based on wall-clock time.
> Anthropic's actual billing period may reset on a fixed calendar date; the two
> will drift slightly at billing boundaries.

### Row 10 — GPU

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
    "5h_tokens": 88000000,          // Starting ceiling for the 5h window (all models)
    "5h_opus_tokens": 35000000,     // Opus share of the 5h window (projection budget)
    "5h_fable_tokens": 35000000,    // Fable share of the 5h window (projection budget)
    "week_opus_tokens": 70000000,   // Starting ceiling for weekly Opus
    "week_fable_tokens": 70000000,  // Starting ceiling for weekly Fable/Mythos
    "week_sonnet_tokens": 440000000 // Starting ceiling for weekly Sonnet+Haiku
  },
  "observed_max": {
    "5h_tokens": 0,          // Auto-learned; set to 0 to reset
    "5h_opus_tokens": 0,
    "5h_fable_tokens": 0,
    "week_opus_tokens": 0,
    "week_fable_tokens": 0,
    "week_sonnet_tokens": 0
  },
  "projection": {
    "opus_5h_rate_window_s": 900,     // Trailing seconds for the Opus 5h burn rate
    "opus_week_rate_window_s": 21600, // Trailing seconds for the Opus weekly burn rate
    "fable_5h_rate_window_s": 900,    // Same, for Fable
    "fable_week_rate_window_s": 21600
  },
  "account": {
    "enabled": true,        // Poll the account /usage endpoint
    "refresh_seconds": 60   // Minimum seconds between account fetches
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
| `defaults.5h_opus_tokens` | `35000000` | Budget used by the Opus · 5h projection bar |
| `defaults.5h_fable_tokens` | `35000000` | Budget used by the Fable · 5h projection bar |
| `defaults.week_opus_tokens` | `70000000` | Starting weekly Opus budget |
| `defaults.week_fable_tokens` | `70000000` | Starting weekly Fable/Mythos budget |
| `defaults.week_sonnet_tokens` | `440000000` | Starting weekly Sonnet+Haiku budget |
| `observed_max.*` | `0` | Auto-bumped whenever usage exceeds the stored value (one key per window, same names as `defaults`); set to `0` to forget the learned ceiling |
| `projection.opus_5h_rate_window_s` | `900` | Trailing window (seconds) for measuring the Opus 5h burn rate |
| `projection.opus_week_rate_window_s` | `21600` | Trailing window (seconds) for the Opus weekly burn rate |
| `projection.fable_5h_rate_window_s` | `900` | Same, for the Fable 5h burn rate |
| `projection.fable_week_rate_window_s` | `21600` | Same, for the Fable weekly burn rate |
| `account.enabled` | `true` | Poll the account usage endpoint (real `/usage` percentages); set `false` for local-estimates-only mode |
| `account.refresh_seconds` | `60` | Minimum seconds between account endpoint fetches |
| `window.x` / `window.y` | `null` | Screen position persisted on close; delete or set to `null` to reset to default |
| `refresh_seconds` | `10` | Polling interval in seconds; lower values increase responsiveness but slightly increase CPU usage |

Configs written by older TokenFollow versions are upgraded automatically: any
missing key (for example the `5h_fable_tokens` / `week_fable_tokens` pair) is
filled in from defaults on the next launch, and your existing values are kept.

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
  "5h_opus_tokens": 0,
  "5h_fable_tokens": 0,
  "week_opus_tokens": 0,
  "week_fable_tokens": 0,
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

* **Local estimates vs. account truth** — the local per-family token counts
  only cover Claude Code on this machine; claude.ai web/mobile usage, other
  machines, and cloud-side agent runs are counted by your account but not by
  the local logs.  Account-synced rows (percentages) do not have this problem.
* **Account sync needs Claude Code credentials** — the sync reads the OAuth
  token from `~/.claude/.credentials.json`; if Claude Code has never logged
  in on this machine (or the token expired and Claude Code hasn't refreshed
  it), account rows fall back to local estimates / `N/A`.
* **Windows-only GPU fallback** — the `perfcounter` path uses Windows-specific
  performance counter names; it will not work on macOS or Linux.
* **Per-project breakdowns** — not supported; all projects are summed together.
* **Dollar cost display** — not shown; token counts only.
* **sparklines / history graphs** — not implemented.
* **Auto-update** — there is no self-update mechanism; pull the repo to update.
* **System tray icon** — not implemented; the overlay is always a visible window.
