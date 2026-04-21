from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class UsageRecord:
    ts: datetime
    model: str
    input: int
    cache_create: int
    cache_read: int
    output: int


def _parse_ts(raw: str) -> datetime:
    # Accept both "...Z" and "...+00:00"
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_line(line: str) -> UsageRecord | None:
    """Parse one JSONL line; return None if malformed or not an assistant usage record."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    msg = obj.get("message") or {}
    usage = msg.get("usage")
    ts_raw = obj.get("timestamp")
    model = msg.get("model")
    if not (usage and ts_raw and model):
        return None
    try:
        ts = _parse_ts(ts_raw)
    except ValueError:
        return None
    return UsageRecord(
        ts=ts,
        model=model,
        input=int(usage.get("input_tokens", 0)),
        cache_create=int(usage.get("cache_creation_input_tokens", 0)),
        cache_read=int(usage.get("cache_read_input_tokens", 0)),
        output=int(usage.get("output_tokens", 0)),
    )


class UsageParser:
    """Walks <projects_root>/**/*.jsonl, reading only new bytes since last scan.

    Offsets are held in memory for the lifetime of the process. On first scan
    every file is read from byte 0; thereafter only the tail past the stored
    offset is read. If a file shrinks between scans it is treated as rotated
    and re-read from 0.
    """

    def __init__(self, projects_root: Path):
        self._root = Path(projects_root)
        self._offsets: Dict[Path, int] = {}
        self._records: List[UsageRecord] = []

    def scan(self) -> List[UsageRecord]:
        if not self._root.exists():
            return list(self._records)
        for path in sorted(self._root.rglob("*.jsonl")):
            try:
                size = path.stat().st_size
            except OSError:                       # pragma: no cover
                continue
            prev = self._offsets.get(path, 0)
            if size < prev:
                prev = 0
            if size == prev:
                continue
            try:
                with path.open("rb") as f:
                    f.seek(prev)
                    data = f.read(size - prev)
            except OSError:                       # pragma: no cover
                continue
            self._offsets[path] = size
            for raw in data.splitlines():
                if not raw.strip():
                    continue
                line = raw.decode("utf-8", errors="replace")
                rec = parse_line(line)
                if rec is not None:
                    self._records.append(rec)
        self._records.sort(key=lambda r: r.ts)
        return list(self._records)

    def save_cache(self, cache_path: Path) -> None:
        """Write current offsets to disk (diagnostic only; not read on startup)."""
        payload = {str(p): off for p, off in self._offsets.items()}
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
