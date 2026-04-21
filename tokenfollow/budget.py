from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from tokenfollow.aggregator import Snapshot


DEFAULTS = {
    "weights": {"cache_read": 0.1},
    "defaults": {
        "5h_tokens": 88_000_000,
        "week_opus_tokens": 70_000_000,
        "week_sonnet_tokens": 440_000_000,
    },
    "observed_max": {
        "5h_tokens": 0,
        "week_opus_tokens": 0,
        "week_sonnet_tokens": 0,
    },
    "window": {"x": None, "y": None},
    "refresh_seconds": 10,
}


class BudgetManager:
    """Owns config.json. Exposes budgets, observed_max, weights, position."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data = self._load_or_init()

    def _load_or_init(self) -> Dict:
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
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def save(self) -> None:
        self._write(self._data)

    @property
    def budgets(self) -> Dict[str, int]:
        d = self._data["defaults"]
        return {"5h": d["5h_tokens"],
                "week_opus": d["week_opus_tokens"],
                "week_sonnet": d["week_sonnet_tokens"]}

    @property
    def observed(self) -> Dict[str, int]:
        o = self._data["observed_max"]
        return {"5h": o["5h_tokens"],
                "week_opus": o["week_opus_tokens"],
                "week_sonnet": o["week_sonnet_tokens"]}

    @property
    def weights(self) -> Dict[str, float]:
        return dict(self._data["weights"])

    @property
    def refresh_seconds(self) -> int:
        return int(self._data["refresh_seconds"])

    @property
    def window_position(self):
        w = self._data["window"]
        return (w.get("x"), w.get("y"))

    def save_position(self, x: Optional[int], y: Optional[int]) -> None:
        self._data["window"]["x"] = x
        self._data["window"]["y"] = y
        self._write(self._data)

    def maybe_bump(self, snap: Snapshot) -> bool:
        changed = False
        pairs = [
            ("5h_tokens", snap.five_hour.used),
            ("week_opus_tokens", snap.week_opus.used),
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
    return json.loads(json.dumps(obj))


def _merge_defaults(data, defaults):
    if not isinstance(defaults, dict):
        return data if data is not None else defaults
    out = dict(defaults)
    if isinstance(data, dict):
        for k, v in defaults.items():
            if k in data:
                out[k] = _merge_defaults(data[k], v)
    return out
