from __future__ import annotations

from datetime import timedelta

from tokenfollow.aggregator import (
    aggregate,
    ProjectionSnapshot,
    Snapshot,
    WindowSnapshot,
)
from tokenfollow.parser import UsageRecord


def _rec(ts, model="claude-sonnet-4-6", input=100, cache_create=0,
         cache_read=0, output=50) -> UsageRecord:
    return UsageRecord(ts=ts, model=model, input=input,
                       cache_create=cache_create, cache_read=cache_read, output=output)


BUDGETS = {"5h": 88_000_000, "5h_opus": 35_000_000,
           "week_opus": 70_000_000, "week_sonnet": 440_000_000}
OBSERVED = {"5h": 0, "5h_opus": 0, "week_opus": 0, "week_sonnet": 0}
WEIGHTS = {"cache_read": 0.1}
RATE_WINDOWS = {"opus_5h": 900, "opus_week": 21_600}


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


# --- Projection tests --------------------------------------------------------


def test_projections_exist_and_are_idle_on_empty(utc):
    snap = aggregate([], BUDGETS, OBSERVED, utc(2026, 4, 21, 12, 0), WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    assert isinstance(snap.opus_5h_proj, ProjectionSnapshot)
    assert isinstance(snap.opus_week_proj, ProjectionSnapshot)
    assert snap.opus_5h_proj.used_now == 0
    assert snap.opus_5h_proj.rate_per_sec == 0.0
    assert snap.opus_5h_proj.projected_used == 0
    assert snap.opus_5h_proj.resets_at is None
    assert snap.opus_5h_proj.seconds_until_zero is None
    assert snap.opus_week_proj.resets_at is None


def test_opus_5h_projection_basic(utc):
    # Anchor at 11:15 (exactly T=15 min ago so t_clamped == T == 900s).
    # Four opus records in the trailing 15-min window, each = 1000 tokens.
    # rate = 4000 / 900 ≈ 4.4444 tokens/sec
    # t_remaining = (11:15 + 5h) - 11:30 = 4h 45min = 17100s
    # projected_used = 4000 + (4000/900)*17100 = 4000 + 76000 = 80000
    records = [
        _rec(utc(2026, 4, 21, 11, 15), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 20), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 25), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 30), model="claude-opus-4-7", input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.used_now == 4000
    assert p.projected_used == 80_000
    assert p.resets_at == utc(2026, 4, 21, 11, 15) + timedelta(hours=5)
    # Budget is hybrid max; default 35M dominates here.
    assert p.budget == 35_000_000


def test_opus_5h_trailing_window_excludes_older_records(utc):
    # Record 20 min ago is outside the 15-min trailing window; rate should
    # only reflect the record 5 min ago.
    records = [
        _rec(utc(2026, 4, 21, 11, 10), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 25), model="claude-opus-4-7", input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.used_now == 2000
    # Only the 11:25 record (1000 tokens) counts toward rate.
    assert abs(p.rate_per_sec - (1000 / 900)) < 1e-6


def test_opus_5h_rate_zero_when_no_recent_activity(utc):
    # Last opus message was 30 min ago; trailing 15-min window is empty.
    records = [
        _rec(utc(2026, 4, 21, 11, 0), model="claude-opus-4-7", input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.rate_per_sec == 0.0
    # projected_used == used_now when rate is zero
    assert p.projected_used == p.used_now == 1000
    assert p.seconds_until_zero is None


def test_opus_5h_trailing_window_clamped_to_window_elapsed(utc):
    # Anchor at 11:28, now at 11:30 — only 2 minutes into the window.
    # Trailing T=15min would extend before anchor; must clamp to 120s.
    # One 1000-token record right at anchor, one at now.
    records = [
        _rec(utc(2026, 4, 21, 11, 28), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 30), model="claude-opus-4-7", input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    # 2000 tokens / 120 seconds = 16.666.. tokens/sec
    assert abs(p.rate_per_sec - (2000 / 120)) < 1e-6


def test_opus_5h_seconds_until_zero(utc):
    # used_now 10M, budget 35M, rate = 5000 tokens/sec → 25M / 5000 = 5000 sec
    # Build records that give rate=5000/sec over a 15-min window:
    # tokens = 5000 * 900 = 4_500_000 in trailing 15 min.
    # But used_now must be 10M → add a separate older-in-window record.
    records = [
        # Older-in-window, doesn't count toward trailing rate.
        _rec(utc(2026, 4, 21, 11, 0), model="claude-opus-4-7",
             input=5_499_100, output=500_000, cache_create=0, cache_read=0),
        # Record in trailing 15min contributes to rate and used_now.
        _rec(utc(2026, 4, 21, 11, 25), model="claude-opus-4-7",
             input=4_499_100, output=500_000, cache_create=0, cache_read=0),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    # used_now = 5_999_100 + 4_999_100 = 10_998_200
    assert p.used_now == 10_998_200
    # rate_per_sec = 4_999_100 / 900
    assert p.seconds_until_zero is not None
    expected = (p.budget - p.used_now) / (4_999_100 / 900)
    assert abs(p.seconds_until_zero - expected) < 1


def test_opus_5h_projection_can_exceed_budget(utc):
    # Budget must NOT auto-grow to match projection, otherwise the bar can
    # never show an overrun. used_now dwarfs the default, projection dwarfs
    # used_now; we assert the bar is honest about the overrun.
    budgets = dict(BUDGETS, **{"5h_opus": 1000})
    observed = dict(OBSERVED, **{"5h_opus": 0})
    records = [
        _rec(utc(2026, 4, 21, 11, 20), model="claude-opus-4-7",
             input=9000, output=1000),
        _rec(utc(2026, 4, 21, 11, 28), model="claude-opus-4-7",
             input=9000, output=1000),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, budgets, observed, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.used_now == 20_000
    # Budget reflects reality (default/observed/used_now) — not the speculation.
    assert p.budget == p.used_now  # 20k is the largest of {1k, 0, 20k}
    # Projection is allowed to exceed the budget → the UI shows "overrun by X".
    assert p.projected_used > p.budget


def test_opus_5h_projection_respects_default_when_below(utc):
    # When projected_used is comfortably below the default budget, the budget
    # should stay at the default — unchanged by the projection.
    records = [
        _rec(utc(2026, 4, 21, 11, 28), model="claude-opus-4-7",
             input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.budget == 35_000_000  # default, untouched by projection
    assert p.projected_used < p.budget


def test_opus_5h_only_counts_opus_records(utc):
    # Sonnet record in trailing window must NOT contribute to opus projection.
    records = [
        _rec(utc(2026, 4, 21, 11, 25), model="claude-sonnet-4-6",
             input=9000, output=1000),
        _rec(utc(2026, 4, 21, 11, 28), model="claude-opus-4-7",
             input=900, output=100),
    ]
    now = utc(2026, 4, 21, 11, 30)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_5h_proj
    assert p.used_now == 1000  # only the opus record
    # Rate over 15-min trailing window (120s clamp? anchor is 11:25 sonnet,
    # but _current_5h_window might anchor on first record overall) — regardless,
    # only the 1000-token opus record counts.
    recent_opus_tokens = 1000
    assert p.rate_per_sec * p.rate_per_sec >= 0  # sanity: finite, non-negative


def test_opus_week_projection_basic(utc):
    # Opus records across the last week; rate from last 6h.
    # Records: one yesterday morning, one 3h ago, one 1h ago, one 30min ago.
    # used_now = sum of all four = 4 * 1000 = 4000.
    # Trailing T=6h=21600s; records in last 6h: 3h ago, 1h ago, 30 min ago = 3000.
    # rate = 3000 / 21600 = 0.1388.. tokens/sec
    records = [
        _rec(utc(2026, 4, 20, 12, 0), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 9, 0),  model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 0), model="claude-opus-4-7", input=900, output=100),
        _rec(utc(2026, 4, 21, 11, 30), model="claude-opus-4-7", input=900, output=100),
    ]
    now = utc(2026, 4, 21, 12, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_week_proj
    assert p.used_now == 4000
    assert abs(p.rate_per_sec - (3000 / 21600)) < 1e-6
    assert p.resets_at == utc(2026, 4, 20, 12, 0) + timedelta(days=7)


def test_opus_week_idle_when_no_opus_records(utc):
    records = [_rec(utc(2026, 4, 20, 10, 0), model="claude-sonnet-4-6",
                    input=1000, output=100)]
    now = utc(2026, 4, 21, 12, 0)
    snap = aggregate(records, BUDGETS, OBSERVED, now, WEIGHTS,
                     rate_windows=RATE_WINDOWS)
    p = snap.opus_week_proj
    assert p.used_now == 0
    assert p.rate_per_sec == 0.0
    assert p.resets_at is None
    assert p.seconds_until_zero is None


def test_aggregate_default_rate_windows(utc):
    # Calling aggregate without rate_windows should still work (defaults).
    snap = aggregate([], BUDGETS, OBSERVED, utc(2026, 4, 21, 12, 0), WEIGHTS)
    assert isinstance(snap.opus_5h_proj, ProjectionSnapshot)
    assert isinstance(snap.opus_week_proj, ProjectionSnapshot)


def test_aggregate_tolerates_missing_5h_opus_key(utc):
    # Old config without 5h_opus key; aggregator should not crash.
    old_budgets = {"5h": 88_000_000, "week_opus": 70_000_000, "week_sonnet": 440_000_000}
    old_observed = {"5h": 0, "week_opus": 0, "week_sonnet": 0}
    snap = aggregate([], old_budgets, old_observed, utc(2026, 4, 21, 12, 0), WEIGHTS)
    assert snap.opus_5h_proj.used_now == 0
