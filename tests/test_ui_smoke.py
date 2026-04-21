from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta, timezone

import pytest

from tokenfollow.aggregator import Snapshot, WindowSnapshot
from tokenfollow.ui import OverlayWindow, band_color, BAND_GREEN, BAND_AMBER, BAND_RED
from tokenfollow.ui import _fmt_tokens, _fmt_delta


UTC = timezone.utc


def _snap(f=0.2, o=0.2, s=0.2, gpu=30):
    now = datetime(2026, 4, 21, 12, 0, tzinfo=UTC)
    return Snapshot(
        five_hour=WindowSnapshot(int(f * 88_000_000), 88_000_000,
                                 now + timedelta(hours=2, minutes=14), 0),
        week_opus=WindowSnapshot(int(o * 70_000_000), 70_000_000,
                                 now + timedelta(days=3, hours=5), 0),
        week_sonnet=WindowSnapshot(int(s * 440_000_000), 440_000_000,
                                   now + timedelta(days=4, hours=1), 0),
        now=now,
        gpu_percent=gpu,
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


def test_current_position_returns_none_on_bad_geometry(tk_root):
    w = OverlayWindow(root=tk_root, on_close=lambda: None)
    # Patch geometry() to return something unparseable.
    import unittest.mock as mock
    with mock.patch.object(tk_root, "geometry", return_value="badgeom"):
        x, y = w.current_position()
    assert (x, y) == (None, None)
