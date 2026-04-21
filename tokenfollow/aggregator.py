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
    return Snapshot(five_hour=five, week_opus=week_opus,
                    week_sonnet=week_sonnet, now=now)
