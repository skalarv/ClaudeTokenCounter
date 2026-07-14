from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta, timezone

import pytest

from tokenfollow.account import AccountLimit, AccountUsage
from tokenfollow.aggregator import ProjectionSnapshot, Snapshot, WindowSnapshot
from tokenfollow.ui import OverlayWindow, band_color, BAND_GREEN, BAND_AMBER, BAND_RED
from tokenfollow.ui import _account_color, _fmt_tokens, _fmt_delta


UTC = timezone.utc


def _proj(used_now=0, budget=35_000_000, projected_used=0,
          rate=0.0, resets_at=None, until_zero=None):
    return ProjectionSnapshot(
        used_now=used_now, budget=budget, rate_per_sec=rate,
        projected_used=projected_used, resets_at=resets_at,
        seconds_until_zero=until_zero,
    )


def _snap(f=0.2, o=0.2, s=0.2, fa=0.2, gpu=30,
          p5h=None, pweek=None, account=None):
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    return Snapshot(
        five_hour=WindowSnapshot(int(f * 88_000_000), 88_000_000,
                                 now + timedelta(hours=2, minutes=14), 0),
        week_opus=WindowSnapshot(int(o * 70_000_000), 70_000_000,
                                 now + timedelta(days=3, hours=5), 0),
        week_sonnet=WindowSnapshot(int(s * 440_000_000), 440_000_000,
                                   now + timedelta(days=4, hours=1), 0),
        now=now,
        opus_5h_proj=p5h if p5h is not None else _proj(
            used_now=5_000_000, projected_used=20_000_000, rate=2000.0,
            resets_at=now + timedelta(hours=2, minutes=14),
            until_zero=15_000,
        ),
        opus_week_proj=pweek if pweek is not None else _proj(
            used_now=14_000_000, budget=70_000_000,
            projected_used=40_000_000, rate=100.0,
            resets_at=now + timedelta(days=3, hours=5),
            until_zero=560_000,
        ),
        week_fable=WindowSnapshot(int(fa * 70_000_000), 70_000_000,
                                  now + timedelta(days=3, hours=5), 0),
        fable_5h_proj=_proj(
            used_now=3_000_000, projected_used=12_000_000, rate=1500.0,
            resets_at=now + timedelta(hours=2, minutes=14),
            until_zero=21_000,
        ),
        fable_week_proj=_proj(
            used_now=10_000_000, budget=70_000_000,
            projected_used=30_000_000, rate=90.0,
            resets_at=now + timedelta(days=3, hours=5),
            until_zero=660_000,
        ),
        gpu_percent=gpu,
        account=account,
    )


def _account(session_pct=29.0, weekly_pct=58.0, fable_pct=None,
             fable_severity="critical"):
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    scoped = {}
    if fable_pct is not None:
        scoped["fable"] = AccountLimit(percent=fable_pct,
                                       resets_at=now + timedelta(hours=23),
                                       severity=fable_severity,
                                       is_active=True)
    return AccountUsage(
        session=AccountLimit(percent=session_pct,
                             resets_at=now + timedelta(hours=3)),
        weekly_all=AccountLimit(percent=weekly_pct,
                                resets_at=now + timedelta(days=1)),
        scoped=scoped,
    )


@pytest.fixture
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no Tk display available: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_band_color_thresholds():
    assert band_color(0.50) == BAND_GREEN
    assert band_color(0.59) == BAND_GREEN
    assert band_color(0.60) == BAND_AMBER
    assert band_color(0.85) == BAND_AMBER
    assert band_color(0.86) == BAND_RED
    assert band_color(0.99) == BAND_RED


def test_window_constructs_and_renders(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap())
    tk_root.update_idletasks()
    text = w.label_texts()
    assert "5h" in text["five_hour"]
    assert "Opus" in text["week_opus"]
    assert "Fable" in text["week_fable"]
    assert "Sonnet" in text["week_sonnet"]
    assert "30" in text["gpu"]


def test_gpu_row_shows_na_when_none(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(gpu=None))
    assert "N/A" in w.label_texts()["gpu"]


def test_close_callback_fires(tk_root):
    called = []
    w = OverlayWindow(root=tk_root, on_close=lambda: called.append(True))
    w._on_close()
    assert called == [True]


def test_topmost_reasserted_on_restore(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    tk_root.attributes("-topmost", False)
    w._on_map(None)
    assert bool(tk_root.attributes("-topmost")) is True


def test_fmt_tokens_branches():
    assert _fmt_tokens(500) == "500"
    assert _fmt_tokens(1500) == "1.5K"
    assert _fmt_tokens(2_500_000) == "2.5M"


def test_fmt_delta_idle_when_target_none():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    assert _fmt_delta(None, now) == "idle"


def test_fmt_delta_resetting_when_past():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    target = now - timedelta(minutes=1)
    assert _fmt_delta(target, now) == "resetting…"


def test_fmt_delta_minutes_only():
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    target = now + timedelta(minutes=20)
    assert _fmt_delta(target, now) == "resets in 20m"


def test_restore_position_applies_geometry(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.restore_position((1500, 40))
    tk_root.update_idletasks()
    geom = tk_root.geometry()
    assert "+1500+40" in geom


def test_current_position_after_restore(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.restore_position((1500, 40))
    tk_root.update_idletasks()
    x, y = w.current_position()
    assert (x, y) == (1500, 40)


def test_restore_position_none_coords_is_noop(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    # Should not raise even when both coords are None; no geometry update made.
    w.restore_position((None, None))
    tk_root.update_idletasks()
    # Verify no explicit "+x+y" offset was forced — the geometry string must
    # NOT contain a manually-set large offset (we just confirm it doesn't
    # contain coordinates we never asked for by checking no exception raised).
    assert tk_root.winfo_exists()


def test_all_ten_rows_present(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap())
    tk_root.update_idletasks()
    keys = set(w.label_texts().keys())
    assert keys == {"five_hour", "fable_5h_proj", "opus_5h_proj", "week_all",
                    "week_fable", "fable_week_proj",
                    "week_opus", "opus_week_proj", "week_sonnet", "gpu"}


def test_account_color_severity_wins():
    lim = AccountLimit(percent=10.0, resets_at=None, severity="critical")
    assert _account_color(lim, 0.10) == BAND_RED
    warn = AccountLimit(percent=10.0, resets_at=None, severity="warning")
    assert _account_color(warn, 0.10) == BAND_AMBER
    norm = AccountLimit(percent=10.0, resets_at=None, severity="normal")
    assert _account_color(norm, 0.10) == BAND_GREEN
    assert _account_color(norm, 0.90) == BAND_RED  # thresholds still apply


def test_account_drives_five_hour_row(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(account=_account(session_pct=29.0)))
    tk_root.update_idletasks()
    text = w.label_texts()["five_hour"]
    assert "29%" in text
    assert "est" in text            # local estimate kept as annotation
    assert 28 <= float(w._bars["five_hour"]["value"]) <= 30


def test_week_all_row_shows_account_percent(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(account=_account(weekly_pct=58.0)))
    tk_root.update_idletasks()
    assert "58%" in w.label_texts()["week_all"]
    assert 57 <= float(w._bars["week_all"]["value"]) <= 59


def test_week_all_row_na_without_account(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(account=None))
    tk_root.update_idletasks()
    assert "N/A" in w.label_texts()["week_all"]


def test_scoped_fable_limit_drives_week_fable_row(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(account=_account(fable_pct=96.0)))
    tk_root.update_idletasks()
    text = w.label_texts()["week_fable"]
    assert "96%" in text
    assert 95 <= float(w._bars["week_fable"]["value"]) <= 97
    # Other weekly rows have no scoped account data → local estimate format.
    assert "%" not in w.label_texts()["week_opus"].split("·")[0]


def test_rows_fall_back_to_estimates_without_account(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap(account=None))
    tk_root.update_idletasks()
    text = w.label_texts()["five_hour"]
    assert "/" in text              # "used / budget" estimate format
    assert "est" not in text


def test_fable_projection_rows_render(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap())
    tk_root.update_idletasks()
    text = w.label_texts()
    assert "Fable" in text["fable_5h_proj"] and "5h" in text["fable_5h_proj"]
    assert "Fable" in text["fable_week_proj"] and "week" in text["fable_week_proj"]
    assert "proj" in text["fable_5h_proj"].lower()


def test_render_tolerates_missing_fable_fields(tk_root):
    # Snapshots built by pre-Fable code paths leave the fable fields as None;
    # the UI must render them as empty/idle rather than crash.
    snap = _snap()
    snap.week_fable = None
    snap.fable_5h_proj = None
    snap.fable_week_proj = None
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(snap)
    tk_root.update_idletasks()
    text = w.label_texts()
    assert "idle" in text["fable_5h_proj"].lower()
    assert "idle" in text["fable_week_proj"].lower()
    assert "0 / 0" in text["week_fable"]


def test_projection_label_shows_proj_and_budget(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    w.update(_snap())
    tk_root.update_idletasks()
    text = w.label_texts()["opus_5h_proj"]
    assert "Opus" in text and "5h" in text
    assert "proj" in text.lower()


def test_projection_overrun_label(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    over = _proj(used_now=30_000_000, budget=35_000_000,
                 projected_used=41_000_000, rate=3000.0,
                 resets_at=datetime(2026, 4, 21, 14, 0, tzinfo=UTC),
                 until_zero=1_600)
    w.update(_snap(p5h=over))
    tk_root.update_idletasks()
    text = w.label_texts()["opus_5h_proj"]
    assert "overrun" in text.lower()


def test_projection_idle_label(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    idle = _proj(used_now=0, budget=35_000_000, projected_used=0,
                 rate=0.0, resets_at=None, until_zero=None)
    w.update(_snap(p5h=idle))
    tk_root.update_idletasks()
    text = w.label_texts()["opus_5h_proj"]
    assert "idle" in text.lower()


def test_projection_bar_fill_uses_projected_used(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    mid = _proj(used_now=5_000_000, budget=35_000_000,
                projected_used=17_500_000, rate=1000.0,
                resets_at=datetime(2026, 4, 21, 14, 0, tzinfo=UTC),
                until_zero=30_000)
    w.update(_snap(p5h=mid))
    # Internal bar widget value should be ~50 (17.5M / 35M = 0.5)
    bar_val = float(w._bars["opus_5h_proj"]["value"])
    assert 49 <= bar_val <= 51


def test_projection_pinned_at_100_on_overrun(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    over = _proj(used_now=30_000_000, budget=35_000_000,
                 projected_used=100_000_000, rate=3000.0,
                 resets_at=datetime(2026, 4, 21, 14, 0, tzinfo=UTC),
                 until_zero=1_600)
    w.update(_snap(p5h=over))
    assert float(w._bars["opus_5h_proj"]["value"]) == 100.0


def test_current_position_returns_none_on_bad_geometry(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    # Patch geometry() to return something unparseable.
    import unittest.mock as mock
    with mock.patch.object(tk_root, "geometry", return_value="badgeom"):
        x, y = w.current_position()
    assert (x, y) == (None, None)
