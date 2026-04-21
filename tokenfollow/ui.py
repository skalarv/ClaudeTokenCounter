from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Callable, Dict, Optional

from tokenfollow.aggregator import Snapshot, WindowSnapshot


BAND_GREEN = "#2e9e4b"
BAND_AMBER = "#d98e0b"
BAND_RED = "#c0392b"


def band_color(fraction: float) -> str:
    if fraction < 0.60:
        return BAND_GREEN
    if fraction <= 0.85:
        return BAND_AMBER
    return BAND_RED


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _fmt_delta(target: Optional[datetime], now: datetime) -> str:
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
    """Four-row overlay: three token bars + GPU."""

    def __init__(self, *, root: Optional[tk.Tk] = None,
                 on_close: Callable[[], None]):
        self.root = root or tk.Tk()
        self.root.title("TokenFollow")
        self.root.geometry("320x180")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        self._on_close_cb = on_close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Map>", self._on_map)

        self._labels: Dict[str, tk.Label] = {}
        self._bars: Dict[str, ttk.Progressbar] = {}
        self._styles: Dict[str, str] = {}
        self._style = ttk.Style(self.root)

        for i, key in enumerate(("five_hour", "week_opus", "week_sonnet", "gpu")):
            lab = tk.Label(self.root, anchor="w", font=("Segoe UI", 9))
            lab.grid(row=i, column=0, sticky="ew", padx=6, pady=(4, 0))
            style_name = f"TokenFollow.{key}.Horizontal.TProgressbar"
            bar = ttk.Progressbar(self.root, length=300, mode="determinate",
                                  maximum=100, style=style_name)
            bar.grid(row=i, column=0, sticky="ew", padx=6, pady=(16, 4))
            self._labels[key] = lab
            self._bars[key] = bar
            self._styles[key] = style_name
        self.root.grid_columnconfigure(0, weight=1)

    def update(self, snap: Snapshot) -> None:
        self._render_token("five_hour", "5h window", snap.five_hour, snap.now)
        self._render_token("week_opus", "Week · Opus", snap.week_opus, snap.now)
        self._render_token("week_sonnet", "Week · Sonnet", snap.week_sonnet, snap.now)
        self._render_gpu(snap.gpu_percent)

    def _render_token(self, key: str, label: str,
                      w: WindowSnapshot, now: datetime) -> None:
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
        return {k: lab["text"] for k, lab in self._labels.items()}

    def _on_map(self, _event) -> None:
        self.root.attributes("-topmost", True)

    def _on_close(self) -> None:
        try:
            self._on_close_cb()
        finally:
            self.root.destroy()

    def restore_position(self, pos) -> None:
        x, y = pos
        if x is not None and y is not None:
            self.root.geometry(f"+{int(x)}+{int(y)}")

    def current_position(self):
        geom = self.root.geometry()
        try:
            coords = geom.split("+")
            return int(coords[-2]), int(coords[-1])
        except (ValueError, IndexError):
            return None, None
