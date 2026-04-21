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


def test_window_anchor_after_gap(utc):
    records = [
        _rec(utc(2026, 4, 21,  8, 0), input=10),
        _rec(utc(2026, 4, 21, 12, 0), input=20),
        _rec(utc(2026, 4, 21, 17, 1), input=30),
    ]
    now = utc(2026, 4, 21, 18, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.five_hour.used == 30 + 50
    assert snap.five_hour.resets_at == utc(2026, 4, 21, 17, 1) + timedelta(hours=5)


def test_exactly_5h_gap_starts_new_window(utc):
    records = [
        _rec(utc(2026, 4, 21,  8, 0), input=10),
        _rec(utc(2026, 4, 21, 13, 0), input=20),
    ]
    now = utc(2026, 4, 21, 13, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.five_hour.used == 20 + 50
    assert snap.five_hour.resets_at == utc(2026, 4, 21, 18, 0)


def test_no_active_window_when_idle(utc):
    records = [_rec(utc(2026, 4, 21, 8, 0), input=10)]
    now = utc(2026, 4, 21, 14, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.five_hour.used == 0
    assert snap.five_hour.resets_at is None


def test_weekly_split_by_family(utc):
    records = [
        _rec(utc(2026, 4, 15, 10, 0), model="claude-opus-4-7",    input=1000, output=100),
        _rec(utc(2026, 4, 16, 10, 0), model="claude-sonnet-4-6",  input=2000, output=200),
        _rec(utc(2026, 4, 17, 10, 0), model="claude-haiku-4-5",   input=300,  output=30),
        _rec(utc(2026, 4,  5, 10, 0), model="claude-opus-4-7",    input=9999, output=9999),
    ]
    now = utc(2026, 4, 21, 12, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS)
    assert snap.week_opus.used == 1000 + 100
    assert snap.week_sonnet.used == (2000 + 200) + (300 + 30)


def test_cache_read_weight(utc):
    records = [_rec(utc(2026, 4, 21, 11, 0), model="claude-opus-4-7",
                    input=0, cache_read=1000, output=0)]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, {"cache_read": 0.1})
    assert snap.five_hour.used == 100


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
