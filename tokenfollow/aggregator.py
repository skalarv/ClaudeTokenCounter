"""aggregator — groups UsageRecord lists into budget-aware window snapshots.

Inputs: a list of :class:`~tokenfollow.parser.UsageRecord` objects plus budget
and weight configuration mappings.
Outputs: a :class:`Snapshot` dataclass suitable for direct consumption by the
UI layer.  The pure :func:`aggregate` function accepts ``now`` as an explicit
parameter so that tests can remain fully deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Mapping, Optional

from tokenfollow.parser import UsageRecord


FIVE_HOURS = timedelta(hours=5)
ONE_WEEK = timedelta(days=7)


@dataclass
class WindowSnapshot:
    """Token counts for one measurement window (5-hour or 7-day).

    ``budget`` is always >= ``used`` (hybrid max of default / observed / used),
    so the fractional fill ``used / budget`` is always in [0, 1].
    """

    used: int
    budget: int
    resets_at: Optional[datetime]
    observed_max: int


@dataclass
class ProjectionSnapshot:
    """Burn-rate projection for Opus usage inside one window.

    ``projected_used`` is ``used_now + rate_per_sec * seconds_until_reset``.
    ``budget`` is the hybrid max of (default, observed, used_now) — deliberately
    NOT inflated by ``projected_used``, so the projection bar can honestly show
    an overrun when ``projected_used > budget``.
    """

    used_now: int
    budget: int
    rate_per_sec: float
    projected_used: int
    resets_at: Optional[datetime]
    seconds_until_zero: Optional[int]


DEFAULT_RATE_WINDOWS = {"opus_5h": 900, "opus_week": 21_600}


@dataclass
class Snapshot:
    """Complete state for one overlay refresh cycle.

    ``gpu_percent`` is set by the caller after :func:`aggregate` returns;
    it is ``None`` when no GPU source is available.
    """

    five_hour: WindowSnapshot
    week_opus: WindowSnapshot
    week_sonnet: WindowSnapshot
    now: datetime
    opus_5h_proj: "ProjectionSnapshot" = None  # type: ignore[assignment]
    opus_week_proj: "ProjectionSnapshot" = None  # type: ignore[assignment]
    gpu_percent: Optional[int] = None


def _counted(rec: UsageRecord, weights: Mapping[str, float]) -> int:
    """Return the weighted token count for a single record."""
    cr = weights.get("cache_read", 0.1)
    return int(rec.input + rec.cache_create + round(rec.cache_read * cr) + rec.output)


def _family(model: str) -> str:
    """Map a model string to ``"opus"``, ``"sonnet"``, ``"haiku"``, or ``"other"``."""
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


def _project(window_records: List[UsageRecord],
             budget_default: int,
             budget_observed: int,
             now: datetime,
             window_end: Optional[datetime],
             anchor: Optional[datetime],
             trailing_seconds: int,
             weights: Mapping[str, float]) -> ProjectionSnapshot:
    """Build a burn-rate projection for one set of in-window records."""
    used_now = sum(_counted(r, weights) for r in window_records)

    if window_end is None or anchor is None:
        # No active window (weekly with no opus records, or idle 5h).
        budget = max(budget_default, budget_observed, used_now)
        return ProjectionSnapshot(
            used_now=used_now, budget=budget, rate_per_sec=0.0,
            projected_used=used_now, resets_at=None, seconds_until_zero=None,
        )

    t_remaining = max(0.0, (window_end - now).total_seconds())

    # Trailing-window rate: sum of tokens from records in [now-T, now],
    # clamped so we never divide by more than the in-window elapsed time.
    trailing_cutoff = now - timedelta(seconds=trailing_seconds)
    lower = max(trailing_cutoff, anchor)
    recent_tokens = sum(_counted(r, weights) for r in window_records
                        if r.ts >= lower)
    elapsed_in_window = (now - anchor).total_seconds()
    t_clamped = max(1.0, min(float(trailing_seconds), elapsed_in_window))
    rate_per_sec = recent_tokens / t_clamped

    projected_used = int(used_now + rate_per_sec * t_remaining)
    budget = max(budget_default, budget_observed, used_now)

    if rate_per_sec <= 0.0 or used_now >= budget:
        seconds_until_zero: Optional[int] = None
    else:
        seconds_until_zero = int((budget - used_now) / rate_per_sec)

    return ProjectionSnapshot(
        used_now=used_now, budget=budget, rate_per_sec=rate_per_sec,
        projected_used=projected_used, resets_at=window_end,
        seconds_until_zero=seconds_until_zero,
    )


def aggregate(records: List[UsageRecord],
              budgets: Mapping[str, int],
              observed: Mapping[str, int],
              now: datetime,
              weights: Mapping[str, float],
              *,
              rate_windows: Optional[Mapping[str, int]] = None) -> Snapshot:
    """Build a :class:`Snapshot` from the full record history up to *now*.

    Args:
        records: All usage records (order does not matter; sorted internally).
        budgets: Default ceiling tokens keyed by ``"5h"``, ``"week_opus"``,
            ``"week_sonnet"``.
        observed: Previously observed maxima (same keys as *budgets*).
        now: Reference timestamp; must be timezone-aware UTC.
        weights: Token-weight overrides, e.g. ``{"cache_read": 0.1}``.

    Returns:
        A fully-populated :class:`Snapshot`.  ``gpu_percent`` is left as
        ``None``; the caller sets it after aggregation.
    """
    records = sorted(records, key=lambda r: r.ts)

    anchor, win_records = _current_5h_window(records, now)
    five_used = sum(_counted(r, weights) for r in win_records)
    five = WindowSnapshot(
        used=five_used,
        budget=max(budgets["5h"], observed["5h"], five_used),
        resets_at=(anchor + FIVE_HOURS) if anchor else None,
        observed_max=observed["5h"],
    )

    cutoff = now - ONE_WEEK
    recent = [r for r in records if r.ts >= cutoff]

    opus_src = [r for r in recent if _family(r.model) == "opus"]
    sonnet_src = [r for r in recent if _family(r.model) in ("sonnet", "haiku")]

    opus_used = sum(_counted(r, weights) for r in opus_src)
    sonnet_used = sum(_counted(r, weights) for r in sonnet_src)
    opus_reset = (opus_src[0].ts + ONE_WEEK) if opus_src else None
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

    rw = dict(DEFAULT_RATE_WINDOWS)
    if rate_windows:
        rw.update(rate_windows)

    opus_in_5h = [r for r in win_records if _family(r.model) == "opus"]
    opus_5h_proj = _project(
        window_records=opus_in_5h,
        budget_default=int(budgets.get("5h_opus", 0)),
        budget_observed=int(observed.get("5h_opus", 0)),
        now=now,
        window_end=(anchor + FIVE_HOURS) if anchor else None,
        anchor=anchor,
        trailing_seconds=int(rw["opus_5h"]),
        weights=weights,
    )

    opus_week_proj = _project(
        window_records=opus_src,
        budget_default=int(budgets["week_opus"]),
        budget_observed=int(observed["week_opus"]),
        now=now,
        window_end=opus_reset,
        anchor=opus_src[0].ts if opus_src else None,
        trailing_seconds=int(rw["opus_week"]),
        weights=weights,
    )

    return Snapshot(five_hour=five, week_opus=week_opus,
                    week_sonnet=week_sonnet, now=now,
                    opus_5h_proj=opus_5h_proj, opus_week_proj=opus_week_proj)
