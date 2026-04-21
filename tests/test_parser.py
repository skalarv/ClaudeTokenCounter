from __future__ import annotations

from datetime import datetime, timezone

from tokenfollow.parser import UsageRecord, parse_line


def test_parse_valid_line():
    line = (
        '{"type":"assistant","timestamp":"2026-04-21T10:00:00Z",'
        '"message":{"model":"claude-opus-4-7",'
        '"usage":{"input_tokens":10,"cache_creation_input_tokens":200,'
        '"cache_read_input_tokens":1000,"output_tokens":50}}}'
    )
    rec = parse_line(line)
    assert rec == UsageRecord(
        ts=datetime(2026, 4, 21, 10, 0, tzinfo=timezone.utc),
        model="claude-opus-4-7",
        input=10, cache_create=200, cache_read=1000, output=50,
    )


import pytest


@pytest.mark.parametrize("line", [
    "",
    "{not json",
    '{"type":"assistant"}',                                     # no message
    '{"type":"assistant","message":{}}',                        # no usage
    '{"timestamp":"2026-04-21T10:00:00Z","message":{"usage":{}}}',  # no model
    '{"timestamp":"not-a-date","message":{"model":"x","usage":{"input_tokens":1}}}',
])
def test_skip_malformed(line):
    assert parse_line(line) is None


from pathlib import Path

from tokenfollow.parser import UsageParser


def test_incremental_reread(projects_root: Path, make_jsonl, utc):
    proj = projects_root / "ProjectA"
    proj.mkdir()
    f = proj / "session1.jsonl"
    f.write_text(
        '{"timestamp":"2026-04-21T10:00:00Z","message":{"model":"claude-sonnet-4-6",'
        '"usage":{"input_tokens":1,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":2}}}\n',
        encoding="utf-8",
    )

    parser = UsageParser(projects_root)
    first = parser.scan()
    assert len(first) == 1

    with f.open("a", encoding="utf-8") as h:
        h.write(
            '{"timestamp":"2026-04-21T10:01:00Z","message":{"model":"claude-sonnet-4-6",'
            '"usage":{"input_tokens":3,"cache_creation_input_tokens":0,'
            '"cache_read_input_tokens":0,"output_tokens":4}}}\n'
        )

    second = parser.scan()
    assert len(second) == 2
    assert second[0].input == 1
    assert second[1].input == 3


def test_truncation_resets_offset(projects_root: Path):
    proj = projects_root / "ProjectA"
    proj.mkdir()
    f = proj / "session.jsonl"
    f.write_text(
        '{"timestamp":"2026-04-21T10:00:00Z","message":{"model":"claude-sonnet-4-6",'
        '"usage":{"input_tokens":1,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":2}}}\n',
        encoding="utf-8",
    )
    parser = UsageParser(projects_root)
    assert len(parser.scan()) == 1

    f.write_text("", encoding="utf-8")
    f.write_text(
        '{"timestamp":"2026-04-21T11:00:00Z","message":{"model":"claude-opus-4-7",'
        '"usage":{"input_tokens":9,"cache_creation_input_tokens":0,'
        '"cache_read_input_tokens":0,"output_tokens":1}}}\n',
        encoding="utf-8",
    )
    result = parser.scan()
    assert len(result) == 2
    assert result[-1].model == "claude-opus-4-7"


def test_missing_projects_dir_is_ok(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    parser = UsageParser(missing)
    assert parser.scan() == []


def test_empty_projects_dir(projects_root: Path):
    parser = UsageParser(projects_root)
    assert parser.scan() == []
