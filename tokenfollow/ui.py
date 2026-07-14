"""ui — tkinter-based always-on-top overlay window for TokenFollow.

Provides pure helpers (:func:`band_color`, :func:`_fmt_tokens`,
:func:`_fmt_delta`, :func:`_account_color`) that convert numeric values to
display strings / colours, and :class:`OverlayWindow` which owns all Tk state
and renders ten rows (5h window, Fable · 5h, Opus · 5h, Week · All,
Week · Fable, Fable · week, Week · Opus, Opus · week, Week · Sonnet, GPU) on
every :meth:`~OverlayWindow.update` call.

When account data from the ``/usage`` endpoint is present in the snapshot,
the matching token bars show the account's real percentage (with the local
token estimate as annotation); otherwise they fall back to the local
estimate alone.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Callable, Dict, Optional

from tokenfollow.account import AccountLimit
from tokenfollow.aggregator import ProjectionSnapshot, Snapshot, WindowSnapshot


BAND_GREEN = "#2e9e4b"
BAND_AMBER = "#d98e0b"
BAND_RED = "#c0392b"


def band_color(fraction: float) -> str:
    """Return the hex colour for a fill fraction: green < 0.60, amber ≤ 0.85, red above.

    Args:
        fraction: A value in [0, 1] representing how full the budget is.

    Returns:
        One of :data:`BAND_GREEN`, :data:`BAND_AMBER`, or :data:`BAND_RED`.
    """
    if fraction < 0.60:
        return BAND_GREEN
    if fraction <= 0.85:
        return BAND_AMBER
    return BAND_RED


def _fmt_tokens(n: int) -> str:
    """Format a token count as a compact string: ``"1.2M"``, ``"34.5K"``, or the raw number."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _account_color(limit: AccountLimit, fraction: float) -> str:
    """Colour for an account-reported limit: severity wins over thresholds."""
    sev = limit.severity.lower()
    if sev in ("critical", "exceeded"):
        return BAND_RED
    if sev == "warning":
        return BAND_AMBER
    return band_color(fraction)


def _fmt_delta(target: Optional[datetime], now: datetime) -> str:
    """Return a human-readable countdown to *target*, ``"idle"``, or ``"resetting…"``."""
    if target is None:
        return "idle"
    total = int((target - now).total_seconds())
    if total <= 0:
        return "resetting…"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {minutes}m"
    return f"resets in {minutes}m"


class OverlayWindow:
    """Ten-row overlay: five token bars, four projection bars, and GPU."""

    def __init__(self, *, root: Optional[tk.Tk] = None,
                 on_close: Callable[[], None]):
        """Create and configure the overlay window.

        Args:
            root: An existing ``tk.Tk`` instance (useful in tests); a new one
                is created when omitted.
            on_close: Called before the window is destroyed so callers can
                persist state (position, cache offsets, etc.).
        """
        self.root = root or tk.Tk()
        self.root.title("TokenFollow")
        self.root.geometry("340x530")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._on_close_cb = on_close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Map>", self._on_map)

        self._labels: Dict[str, tk.Label] = {}
        self._bars: Dict[str, ttk.Progressbar] = {}
        self._styles: Dict[str, str] = {}
        self._style = ttk.Style(self.root)

        for i, key in enumerate(("five_hour", "fable_5h_proj", "opus_5h_proj",
                                 "week_all", "week_fable", "fable_week_proj",
                                 "week_opus", "opus_week_proj",
                                 "week_sonnet", "gpu")):
            lab = tk.Label(self.root, anchor="w", font=("Segoe UI", 9))
            lab.grid(row=i * 2, column=0, sticky="ew", padx=6, pady=(4, 0))
            style_name = f"TokenFollow.{key}.Horizontal.TProgressbar"
            bar = ttk.Progressbar(self.root, length=320, mode="determinate",
                                  maximum=100, style=style_name)
            bar.grid(row=i * 2 + 1, column=0, sticky="ew", padx=6, pady=(0, 4))
            self._labels[key] = lab
            self._bars[key] = bar
            self._styles[key] = style_name
        self.root.grid_columnconfigure(0, weight=1)

    def update(self, snap: Snapshot) -> None:
        """Refresh all ten rows from *snap*."""
        acct = snap.account
        scoped = acct.scoped if acct is not None else {}
        self._render_token("five_hour", "5h window", snap.five_hour, snap.now,
                           acct=acct.session if acct is not None else None)
        self._render_projection("fable_5h_proj", "Fable · 5h",
                                snap.fable_5h_proj, snap.now)
        self._render_projection("opus_5h_proj", "Opus · 5h",
                                snap.opus_5h_proj, snap.now)
        self._render_account("week_all", "Week · All",
                             acct.weekly_all if acct is not None else None,
                             snap.now)
        self._render_token("week_fable", "Week · Fable",
                           snap.week_fable, snap.now,
                           acct=scoped.get("fable"))
        self._render_projection("fable_week_proj", "Fable · week",
                                snap.fable_week_proj, snap.now)
        self._render_token("week_opus", "Week · Opus", snap.week_opus,
                           snap.now, acct=scoped.get("opus"))
        self._render_projection("opus_week_proj", "Opus · week",
                                snap.opus_week_proj, snap.now)
        self._render_token("week_sonnet", "Week · Sonnet",
                           snap.week_sonnet, snap.now,
                           acct=scoped.get("sonnet"))
        self._render_gpu(snap.gpu_percent)

    def _render_token(self, key: str, label: str,
                      w: Optional[WindowSnapshot], now: datetime,
                      acct: Optional[AccountLimit] = None) -> None:
        if w is None:
            w = WindowSnapshot(used=0, budget=0, resets_at=None, observed_max=0)
        if acct is not None:
            # Account truth: the bar shows the real percentage from the
            # /usage endpoint; the local token count stays as annotation.
            frac = max(0.0, min(1.0, acct.percent / 100.0))
            color = _account_color(acct, frac)
            self._style.configure(self._styles[key], background=color,
                                  troughcolor="#222", bordercolor="#222")
            self._bars[key]["value"] = frac * 100
            self._labels[key]["text"] = (
                f"{label}   {acct.percent:.0f}%   ·   est {_fmt_tokens(w.used)}"
                f"   ·   {_fmt_delta(acct.resets_at, now)}"
            )
            return
        frac = (w.used / w.budget) if w.budget > 0 else 0.0
        frac = max(0.0, min(1.0, frac))
        color = band_color(frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = frac * 100
        self._labels[key]["text"] = (
            f"{label}   {_fmt_tokens(w.used)} / {_fmt_tokens(w.budget)}   ·   "
            f"{_fmt_delta(w.resets_at, now)}"
        )

    def _render_account(self, key: str, label: str,
                        acct: Optional[AccountLimit], now: datetime) -> None:
        """Render a row that only exists as account data (no local estimate)."""
        if acct is None:
            self._bars[key]["value"] = 0
            self._style.configure(self._styles[key], background="#555",
                                  troughcolor="#222", bordercolor="#222")
            self._labels[key]["text"] = f"{label}   N/A"
            return
        frac = max(0.0, min(1.0, acct.percent / 100.0))
        color = _account_color(acct, frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = frac * 100
        self._labels[key]["text"] = (
            f"{label}   {acct.percent:.0f}%   ·   "
            f"{_fmt_delta(acct.resets_at, now)}"
        )

    def _render_projection(self, key: str, label: str,
                           proj: Optional[ProjectionSnapshot],
                           now: datetime) -> None:
        if proj is None or proj.resets_at is None:
            self._bars[key]["value"] = 0
            self._style.configure(self._styles[key], background="#555",
                                  troughcolor="#222", bordercolor="#222")
            self._labels[key]["text"] = f"{label}   idle"
            return
        frac = (proj.projected_used / proj.budget) if proj.budget > 0 else 0.0
        frac = max(0.0, min(1.0, frac))
        color = band_color(frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = frac * 100
        if proj.projected_used > proj.budget:
            detail = f"overrun by {_fmt_tokens(proj.projected_used - proj.budget)}"
        else:
            detail = (f"proj {_fmt_tokens(proj.projected_used)} / "
                      f"{_fmt_tokens(proj.budget)} @ reset")
        self._labels[key]["text"] = (
            f"{label}   {detail}   ·   {_fmt_delta(proj.resets_at, now)}"
        )

    def _render_gpu(self, percent: Optional[int]) -> None:
        key = "gpu"
        if percent is None:
            self._bars[key]["value"] = 0
            self._style.configure(self._styles[key], background="#555",
                                  troughcolor="#222", bordercolor="#222")
            self._labels[key]["text"] = "GPU   N/A"
            return
        frac = max(0.0, min(1.0, percent / 100.0))
        color = band_color(frac)
        self._style.configure(self._styles[key], background=color,
                              troughcolor="#222", bordercolor="#222")
        self._bars[key]["value"] = percent
        self._labels[key]["text"] = f"GPU   {percent} %"

    def label_texts(self) -> Dict[str, str]:
        """Return a ``{key: label_text}`` dict for all ten rows (test helper)."""
        return {k: lab["text"] for k, lab in self._labels.items()}

    def _on_map(self, _event) -> None:
        self.root.attributes("-topmost", True)

    def _on_close(self) -> None:
        try:
            self._on_close_cb()
        finally:
            self.root.destroy()

    def restore_position(self, pos) -> None:
        """Move the window to *pos* ``(x, y)``; no-op if either coordinate is ``None``."""
        x, y = pos
        if x is not None and y is not None:
            self.root.geometry(f"+{int(x)}+{int(y)}")

    def current_position(self):
        """Return the current ``(x, y)`` screen position, or ``(None, None)`` if unreadable."""
        geom = self.root.geometry()
        try:
            coords = geom.split("+")
            return int(coords[-2]), int(coords[-1])
        except (ValueError, IndexError):
            return None, None
