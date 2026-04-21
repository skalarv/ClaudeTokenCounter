"""Shared pytest fixtures for TokenFollow tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pytest


def _jsonl_line(ts: datetime, model: str, input_t: int = 100,
                cache_create: int = 0, cache_read: int = 0,
                output_t: int = 50) -> str:
    """Build a single JSONL line mimicking Claude Code's assistant-message shape."""
    return json.dumps({
        "type": "assistant",
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_t,
                "cache_creation_input_tokens": cache_create,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_t,
                "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
            },
        },
    })


@pytest.fixture
def make_jsonl(tmp_path: Path):
    """Factory: write a JSONL file with given records and return its path."""
    def _factory(name: str, records: Iterable[dict]) -> Path:
        lines = []
        for r in records:
            lines.append(_jsonl_line(
                ts=r["ts"],
                model=r.get("model", "claude-sonnet-4-6"),
                input_t=r.get("input", 100),
                cache_create=r.get("cache_create", 0),
                cache_read=r.get("cache_read", 0),
                output_t=r.get("output", 50),
            ))
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p
    return _factory


@pytest.fixture
def projects_root(tmp_path: Path) -> Path:
    """Empty fake ~/.claude/projects root."""
    root = tmp_path / "projects"
    root.mkdir()
    return root


@pytest.fixture
def utc():
    """Shorthand for building UTC datetimes: utc(2026, 4, 21, 10, 0)."""
    def _make(*args) -> datetime:
        return datetime(*args, tzinfo=timezone.utc)
    return _make
