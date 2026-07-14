from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from tokenfollow.account import (
    AccountLimit,
    AccountUsage,
    AccountUsageMonitor,
    parse_usage_payload,
    read_oauth_token,
)


UTC = timezone.utc


# --- read_oauth_token ---------------------------------------------------------


def test_token_top_level(tmp_path: Path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"accessToken": "tok-123"}), encoding="utf-8")
    assert read_oauth_token(p) == "tok-123"


def test_token_nested_one_level(tmp_path: Path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-456"}}),
                 encoding="utf-8")
    assert read_oauth_token(p) == "tok-456"


def test_token_missing_file(tmp_path: Path):
    assert read_oauth_token(tmp_path / "nope.json") is None


def test_token_bad_json(tmp_path: Path):
    p = tmp_path / "creds.json"
    p.write_text("{not json", encoding="utf-8")
    assert read_oauth_token(p) is None


def test_token_absent_in_json(tmp_path: Path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"other": {"refreshToken": "x"}, "n": 1}),
                 encoding="utf-8")
    assert read_oauth_token(p) is None


def test_token_json_not_dict(tmp_path: Path):
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert read_oauth_token(p) is None


# --- parse_usage_payload ------------------------------------------------------


def _real_shape_payload() -> str:
    """Condensed copy of the live /usage response shape."""
    return json.dumps({
        "five_hour": {"utilization": 29.0,
                      "resets_at": "2026-07-14T18:19:59.543467+03:00"},
        "seven_day": {"utilization": 58.0,
                      "resets_at": "2026-07-15T13:59:59.543501+03:00"},
        "limits": [
            {"kind": "session", "group": "session", "percent": 29,
             "severity": "normal",
             "resets_at": "2026-07-14T18:19:59.543467+03:00",
             "scope": None, "is_active": False},
            {"kind": "weekly_all", "group": "weekly", "percent": 58,
             "severity": "normal",
             "resets_at": "2026-07-15T13:59:59.543501+03:00",
             "scope": None, "is_active": False},
            {"kind": "weekly_scoped", "group": "weekly", "percent": 96,
             "severity": "critical",
             "resets_at": "2026-07-15T13:59:59.54383+03:00",
             "scope": {"model": {"id": None, "display_name": "Fable"},
                       "surface": None},
             "is_active": True},
        ],
    })


def test_parse_real_shape():
    u = parse_usage_payload(_real_shape_payload())
    assert u is not None
    assert u.session.percent == 29
    assert u.session.severity == "normal"
    # +03:00 offset normalised to UTC.
    assert u.session.resets_at == datetime(2026, 7, 14, 15, 19, 59, 543467,
                                           tzinfo=UTC)
    assert u.weekly_all.percent == 58
    assert u.scoped["fable"].percent == 96
    assert u.scoped["fable"].severity == "critical"
    assert u.scoped["fable"].is_active is True


def test_parse_fallback_five_hour_seven_day():
    payload = json.dumps({
        "five_hour": {"utilization": 12.5, "resets_at": "2026-07-14T18:00:00Z"},
        "seven_day": {"utilization": 40.0, "resets_at": None},
    })
    u = parse_usage_payload(payload)
    assert u.session.percent == 12.5
    assert u.session.resets_at == datetime(2026, 7, 14, 18, 0, tzinfo=UTC)
    assert u.weekly_all.percent == 40.0
    assert u.weekly_all.resets_at is None


def test_parse_skips_malformed_limit_entries():
    payload = json.dumps({
        "limits": [
            "not-a-dict",
            {"kind": "unknown_kind", "percent": 10},
            {"kind": "weekly_scoped", "percent": 20, "scope": {}},
            {"kind": "session", "percent": 5, "severity": None,
             "resets_at": "garbage"},
        ],
    })
    u = parse_usage_payload(payload)
    assert u.session.percent == 5
    assert u.session.severity == "normal"     # None coerced to default
    assert u.session.resets_at is None        # unparseable timestamp
    assert u.scoped == {}                     # scoped without model name skipped


def test_parse_naive_timestamp_treated_as_utc():
    payload = json.dumps({
        "limits": [{"kind": "session", "percent": 1,
                    "resets_at": "2026-07-14T18:00:00"}],
    })
    u = parse_usage_payload(payload)
    assert u.session.resets_at == datetime(2026, 7, 14, 18, 0, tzinfo=UTC)


def test_parse_empty_or_bad_payload():
    assert parse_usage_payload("{ nope") is None
    assert parse_usage_payload(json.dumps([1, 2])) is None
    assert parse_usage_payload(json.dumps({})) is None
    assert parse_usage_payload(json.dumps({"five_hour": {"utilization": None},
                                           "seven_day": None})) is None


# --- AccountUsageMonitor ------------------------------------------------------


def _creds(tmp_path: Path) -> Path:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"claudeAiOauth": {"accessToken": "tok-789"}}),
                 encoding="utf-8")
    return p


def _sync(thunk):
    thunk()


def test_monitor_fetch_success(tmp_path: Path):
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env")
        return SimpleNamespace(returncode=0, stdout=_real_shape_payload())

    mon = AccountUsageMonitor(_creds(tmp_path), 60, runner=runner,
                              spawner=_sync)
    usage = mon.read(datetime(2026, 7, 14, 12, 0, tzinfo=UTC))
    # First read spawns synchronously, so the result may land after the
    # return; a second read exposes the cached value either way.
    usage = mon.read(datetime(2026, 7, 14, 12, 0, 5, tzinfo=UTC))
    assert isinstance(usage, AccountUsage)
    assert usage.session.percent == 29
    # Token travels via env, never argv.
    assert seen["env"]["TOKENFOLLOW_OAUTH"] == "tok-789"
    assert all("tok-789" not in part for part in seen["cmd"])


def test_monitor_caches_within_refresh_window(tmp_path: Path):
    calls = []

    def runner(cmd, **kw):
        calls.append(1)
        return SimpleNamespace(returncode=0, stdout=_real_shape_payload())

    mon = AccountUsageMonitor(_creds(tmp_path), 60, runner=runner,
                              spawner=_sync)
    t0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    mon.read(t0)
    mon.read(t0 + timedelta(seconds=30))
    assert len(calls) == 1
    mon.read(t0 + timedelta(seconds=61))
    assert len(calls) == 2


def test_monitor_keeps_last_good_on_failure(tmp_path: Path):
    responses = [SimpleNamespace(returncode=0, stdout=_real_shape_payload()),
                 SimpleNamespace(returncode=1, stdout="")]

    def runner(cmd, **kw):
        return responses.pop(0)

    mon = AccountUsageMonitor(_creds(tmp_path), 60, runner=runner,
                              spawner=_sync)
    t0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    first = mon.read(t0) or mon.read(t0)
    assert first.session.percent == 29
    second = mon.read(t0 + timedelta(seconds=61))
    assert second is not None and second.session.percent == 29


def test_monitor_runner_exception_returns_none(tmp_path: Path):
    def runner(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    mon = AccountUsageMonitor(_creds(tmp_path), 60, runner=runner,
                              spawner=_sync)
    assert mon.read(datetime(2026, 7, 14, 12, 0, tzinfo=UTC)) is None


def test_monitor_missing_credentials(tmp_path: Path):
    calls = []

    def runner(cmd, **kw):                       # pragma: no cover
        calls.append(1)
        return SimpleNamespace(returncode=0, stdout="{}")

    mon = AccountUsageMonitor(tmp_path / "absent.json", 60, runner=runner,
                              spawner=_sync)
    assert mon.read(datetime(2026, 7, 14, 12, 0, tzinfo=UTC)) is None
    assert calls == []                           # never even ran the command


def test_monitor_garbage_stdout(tmp_path: Path):
    def runner(cmd, **kw):
        return SimpleNamespace(returncode=0, stdout="<html>proxy error</html>")

    mon = AccountUsageMonitor(_creds(tmp_path), 60, runner=runner,
                              spawner=_sync)
    mon.read(datetime(2026, 7, 14, 12, 0, tzinfo=UTC))
    assert mon.read(datetime(2026, 7, 14, 12, 0, 1, tzinfo=UTC)) is None


def test_monitor_default_spawner_runs_on_thread():
    done = threading.Event()
    AccountUsageMonitor._spawn_thread(done.set)
    assert done.wait(timeout=5)


def test_monitor_no_refetch_while_in_flight(tmp_path: Path):
    # A spawner that defers execution simulates a slow in-flight fetch.
    pending = []
    mon = AccountUsageMonitor(_creds(tmp_path), 60,
                              runner=lambda cmd, **kw: SimpleNamespace(
                                  returncode=0, stdout=_real_shape_payload()),
                              spawner=pending.append)
    t0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
    mon.read(t0)
    mon.read(t0 + timedelta(seconds=120))        # stale, but fetch in flight
    assert len(pending) == 1
    pending[0]()                                 # fetch completes
    assert mon.read(t0 + timedelta(seconds=121)).session.percent == 29
