from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tokenfollow.aggregator import ProjectionSnapshot, Snapshot, WindowSnapshot
from tokenfollow.budget import BudgetManager


def test_first_run_creates_config(tmp_path: Path):
    cfg = tmp_path / "config.json"
    assert not cfg.exists()
    bm = BudgetManager(cfg)
    assert cfg.exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["defaults"]["5h_tokens"] == 88_000_000
    assert data["weights"]["cache_read"] == 0.1
    assert data["observed_max"]["5h_tokens"] == 0
    assert bm.refresh_seconds == 10


def test_corrupted_config_moves_to_bak(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    BudgetManager(cfg)
    assert (tmp_path / "config.json.bak").exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert "defaults" in data


def _ws(used, budget, observed_max):
    return WindowSnapshot(used=used, budget=budget,
                          resets_at=None, observed_max=observed_max)


def _proj(used_now):
    return ProjectionSnapshot(
        used_now=used_now, budget=35_000_000, rate_per_sec=0.0,
        projected_used=used_now, resets_at=None, seconds_until_zero=None,
    )


def _snap(five_used, opus_used, sonnet_used, opus_5h_used=0):
    return Snapshot(
        five_hour=_ws(five_used, 88_000_000, 0),
        week_opus=_ws(opus_used, 70_000_000, 0),
        week_sonnet=_ws(sonnet_used, 440_000_000, 0),
        now=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        opus_5h_proj=_proj(opus_5h_used),
        opus_week_proj=_proj(opus_used),
    )


def test_observed_bump_on_exceed(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    snap = _snap(five_used=100_000_000, opus_used=0, sonnet_used=0)
    changed = bm.maybe_bump(snap)
    assert changed is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["observed_max"]["5h_tokens"] == 100_000_000


def test_observed_never_decreases(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    bm.maybe_bump(_snap(100_000_000, 0, 0))
    changed = bm.maybe_bump(_snap(50_000_000, 0, 0))
    assert changed is False
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["observed_max"]["5h_tokens"] == 100_000_000


def test_budgets_and_weights_exposed(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    assert bm.budgets == {"5h": 88_000_000,
                          "5h_opus": 35_000_000,
                          "week_opus": 70_000_000,
                          "week_sonnet": 440_000_000}
    assert bm.observed == {"5h": 0, "5h_opus": 0,
                           "week_opus": 0, "week_sonnet": 0}
    assert bm.weights == {"cache_read": 0.1}


def test_position_roundtrip(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm1 = BudgetManager(cfg)
    assert bm1.window_position == (None, None)
    bm1.save_position(1500, 40)
    bm2 = BudgetManager(cfg)
    assert bm2.window_position == (1500, 40)


def test_partial_config_merged_with_defaults(tmp_path: Path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"refresh_seconds": 5}), encoding="utf-8")
    bm = BudgetManager(cfg)
    assert bm.refresh_seconds == 5
    assert bm.budgets["5h"] == 88_000_000


def test_save_persists(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    # Mutate via maybe_bump (not strictly necessary; save() always writes).
    bm.save()
    assert cfg.exists()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["defaults"]["5h_tokens"] == 88_000_000


def test_merge_with_non_dict_default_value(tmp_path: Path):
    # Force a partial config whose value is not a dict at a recursive level.
    cfg = tmp_path / "config.json"
    # refresh_seconds in DEFAULTS is an int (not a dict). User overrides it.
    cfg.write_text(json.dumps({"refresh_seconds": 7,
                               "weights": {"cache_read": 0.05}}),
                   encoding="utf-8")
    bm = BudgetManager(cfg)
    assert bm.refresh_seconds == 7
    assert bm.weights == {"cache_read": 0.05}
    assert bm.budgets["5h"] == 88_000_000  # filled from defaults


def test_first_run_has_5h_opus_defaults(tmp_path: Path):
    cfg = tmp_path / "config.json"
    BudgetManager(cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["defaults"]["5h_opus_tokens"] == 35_000_000
    assert data["observed_max"]["5h_opus_tokens"] == 0


def test_first_run_has_rate_window_defaults(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["projection"]["opus_5h_rate_window_s"] == 900
    assert data["projection"]["opus_week_rate_window_s"] == 21_600
    assert bm.rate_windows == {"opus_5h": 900, "opus_week": 21_600}


def test_budgets_includes_5h_opus(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    assert bm.budgets["5h_opus"] == 35_000_000
    assert bm.observed["5h_opus"] == 0


def test_maybe_bump_5h_opus_from_projection(tmp_path: Path):
    cfg = tmp_path / "config.json"
    bm = BudgetManager(cfg)
    snap = _snap(five_used=0, opus_used=0, sonnet_used=0,
                 opus_5h_used=40_000_000)
    changed = bm.maybe_bump(snap)
    assert changed is True
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["observed_max"]["5h_opus_tokens"] == 40_000_000


def test_merge_data_not_dict_when_defaults_is_dict(tmp_path: Path):
    # Write a config where a sub-key that is normally a dict is replaced with
    # a scalar — _merge_defaults hits the isinstance(data, dict) == False branch.
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"weights": "not-a-dict"}), encoding="utf-8")
    bm = BudgetManager(cfg)
    # The whole defaults["weights"] dict should be used since data["weights"]
    # is not a dict, so _merge_defaults returns it as-is and out["weights"]
    # stays as the defaults value.
    assert bm.budgets["5h"] == 88_000_000
