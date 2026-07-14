"""budget — persists and exposes user-editable token budgets via ``config.json``.

Inputs: ``config.json`` next to the entry-point script (created with
:data:`DEFAULTS` when absent or corrupted).
Outputs: budget / observed / weight mappings consumed by
:func:`~tokenfollow.aggregator.aggregate`, plus window-position persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from tokenfollow.aggregator import Snapshot


DEFAULTS = {
    "weights": {"cache_read": 0.1},
    "defaults": {
        "5h_tokens": 88_000_000,
        "5h_opus_tokens": 35_000_000,
        "5h_fable_tokens": 35_000_000,
        "week_opus_tokens": 70_000_000,
        "week_fable_tokens": 70_000_000,
        "week_sonnet_tokens": 440_000_000,
    },
    "observed_max": {
        "5h_tokens": 0,
        "5h_opus_tokens": 0,
        "5h_fable_tokens": 0,
        "week_opus_tokens": 0,
        "week_fable_tokens": 0,
        "week_sonnet_tokens": 0,
    },
    "projection": {
        "opus_5h_rate_window_s": 900,
        "opus_week_rate_window_s": 21_600,
        "fable_5h_rate_window_s": 900,
        "fable_week_rate_window_s": 21_600,
    },
    "account": {"enabled": True, "refresh_seconds": 60},
    "window": {"x": None, "y": None},
    "refresh_seconds": 10,
}


class BudgetManager:
    """Owns config.json. Exposes budgets, observed_max, weights, position."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data = self._load_or_init()

    def _load_or_init(self) -> Dict:
        """Load ``config.json``, creating or restoring it from defaults if needed."""
        if not self._path.exists():
            data = _deepcopy(DEFAULTS)
            self._write(data)
            return data
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._path.replace(self._path.with_suffix(self._path.suffix + ".bak"))
            data = _deepcopy(DEFAULTS)
            self._write(data)
            return data
        return _merge_defaults(data, DEFAULTS)

    def _write(self, data: Dict) -> None:
        """Serialise *data* to ``config.json`` (pretty-printed)."""
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save(self) -> None:
        """Flush the current in-memory config to disk."""
        self._write(self._data)

    @property
    def budgets(self) -> Dict[str, int]:
        """Default token ceilings keyed by ``"5h"``, ``"5h_opus"``, ``"5h_fable"``, ``"week_opus"``, ``"week_fable"``, ``"week_sonnet"``."""
        d = self._data["defaults"]
        return {"5h": d["5h_tokens"],
                "5h_opus": d["5h_opus_tokens"],
                "5h_fable": d["5h_fable_tokens"],
                "week_opus": d["week_opus_tokens"],
                "week_fable": d["week_fable_tokens"],
                "week_sonnet": d["week_sonnet_tokens"]}

    @property
    def observed(self) -> Dict[str, int]:
        """Auto-learned maximum token counts (same keys as :attr:`budgets`)."""
        o = self._data["observed_max"]
        return {"5h": o["5h_tokens"],
                "5h_opus": o["5h_opus_tokens"],
                "5h_fable": o["5h_fable_tokens"],
                "week_opus": o["week_opus_tokens"],
                "week_fable": o["week_fable_tokens"],
                "week_sonnet": o["week_sonnet_tokens"]}

    @property
    def rate_windows(self) -> Dict[str, int]:
        """Trailing-window seconds for burn-rate projections."""
        p = self._data["projection"]
        return {"opus_5h": int(p["opus_5h_rate_window_s"]),
                "opus_week": int(p["opus_week_rate_window_s"]),
                "fable_5h": int(p["fable_5h_rate_window_s"]),
                "fable_week": int(p["fable_week_rate_window_s"])}

    @property
    def weights(self) -> Dict[str, float]:
        """Token-weight multipliers, e.g. ``{"cache_read": 0.1}``."""
        return dict(self._data["weights"])

    @property
    def refresh_seconds(self) -> int:
        """Polling interval in seconds (default 10)."""
        return int(self._data["refresh_seconds"])

    @property
    def account_enabled(self) -> bool:
        """Whether to poll the account /usage endpoint (default True)."""
        return bool(self._data["account"]["enabled"])

    @property
    def account_refresh_seconds(self) -> int:
        """Minimum seconds between account endpoint fetches (default 60)."""
        return int(self._data["account"]["refresh_seconds"])

    @property
    def window_position(self):
        """Last saved ``(x, y)`` screen coordinates, or ``(None, None)``."""
        w = self._data["window"]
        return (w.get("x"), w.get("y"))

    def save_position(self, x: Optional[int], y: Optional[int]) -> None:
        """Persist the overlay's screen coordinates to ``config.json``."""
        self._data["window"]["x"] = x
        self._data["window"]["y"] = y
        self._write(self._data)

    def maybe_bump(self, snap: Snapshot) -> bool:
        """Update ``observed_max`` if any window in *snap* exceeds the stored peak.

        Returns:
            ``True`` if at least one value was bumped and the file was written.
        """
        changed = False
        pairs = [
            ("5h_tokens", snap.five_hour.used),
            ("5h_opus_tokens",
             snap.opus_5h_proj.used_now if snap.opus_5h_proj is not None else 0),
            ("5h_fable_tokens",
             snap.fable_5h_proj.used_now if snap.fable_5h_proj is not None else 0),
            ("week_opus_tokens", snap.week_opus.used),
            ("week_fable_tokens",
             snap.week_fable.used if snap.week_fable is not None else 0),
            ("week_sonnet_tokens", snap.week_sonnet.used),
        ]
        for key, used in pairs:
            if used > self._data["observed_max"][key]:
                self._data["observed_max"][key] = used
                changed = True
        if changed:
            self._write(self._data)
        return changed


def _deepcopy(obj):
    """JSON-round-trip deep copy (no external deps required)."""
    return json.loads(json.dumps(obj))


def _merge_defaults(data, defaults):
    """Recursively fill any missing keys in *data* from *defaults*."""
    if not isinstance(defaults, dict):
        return data if data is not None else defaults
    out = dict(defaults)
    if isinstance(data, dict):
        for k, v in defaults.items():
            if k in data:
                out[k] = _merge_defaults(data[k], v)
    return out
