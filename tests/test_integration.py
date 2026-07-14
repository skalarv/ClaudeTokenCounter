from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.aggregator import aggregate
from tokenfollow.budget import BudgetManager
from tokenfollow.parser import UsageParser


UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures"


def _scenario(tmp_path, fixture_name, now):
    projects = tmp_path / "projects" / "FakeProject"
    projects.mkdir(parents=True)
    shutil.copy(FIXTURES / fixture_name, projects / fixture_name)
    parser = UsageParser(tmp_path / "projects")
    records = parser.scan()
    bm = BudgetManager(tmp_path / "config.json")
    snap = aggregate(records, bm.budgets, bm.observed, now, bm.weights,
                     rate_windows=bm.rate_windows)
    return snap


def test_golden_fresh(tmp_path: Path):
    snap = _scenario(tmp_path, "fresh.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    assert snap.five_hour.used == 1200
    assert snap.five_hour.resets_at is not None
    assert snap.week_opus.used == 0
    assert snap.week_sonnet.used == 1200


def test_golden_mid_window(tmp_path: Path):
    snap = _scenario(tmp_path, "mid_window.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    # per line: 500k + 1M + round(2M*0.1) + 100k = 1_800_000; ×2 = 3_600_000
    assert snap.five_hour.used == 3_600_000
    assert snap.week_opus.used == 3_600_000


def test_golden_opus_near_cap(tmp_path: Path):
    snap = _scenario(tmp_path, "opus_near_cap.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    # per line: 15M + 5M + round(10M*0.1) + 2M = 23_000_000; 3 lines in last 7d
    assert snap.week_opus.used == 69_000_000
    assert snap.week_opus.used < snap.week_opus.budget
    assert snap.five_hour.used == 23_000_000


def test_golden_after_idle(tmp_path: Path):
    snap = _scenario(tmp_path, "after_idle.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    assert snap.five_hour.used == 0
    assert snap.five_hour.resets_at is None
    assert snap.week_sonnet.used == 600


def test_golden_fable_mixed(tmp_path: Path):
    snap = _scenario(tmp_path, "fable_mixed.jsonl",
                     datetime(2026, 4, 21, 12, 0, tzinfo=UTC))
    # per fable line: 500k + 1M + round(2M*0.1) + 100k = 1_800_000; ×2 lines
    assert snap.week_fable.used == 3_600_000
    # 5h window anchored at 10:30 holds one fable line + the sonnet line.
    assert snap.five_hour.used == 1_800_000 + 150_000
    assert snap.week_sonnet.used == 150_000
    assert snap.week_opus.used == 0
    assert snap.fable_5h_proj.used_now == 1_800_000
    assert snap.fable_week_proj.used_now == 3_600_000
    assert snap.fable_week_proj.resets_at == \
        datetime(2026, 4, 25, 9, 0, tzinfo=UTC)
