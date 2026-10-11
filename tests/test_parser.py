"""Tests for accepted log records and safe rejection of malformed lines."""

from datetime import datetime

import pytest

from logslice.parser import Level, Record, parse_line


@pytest.mark.parametrize("separator", [" ", "T"])
@pytest.mark.parametrize(
    ("fraction", "microsecond"),
    [("", 0), (".1", 100000), (".123", 123000), (".123456", 123456)],
)
def test_timestamp_forms(separator, fraction, microsecond):
    line = f"2026-10-10{separator}12:00:00{fraction} ERROR Disk full"

    record = parse_line(line)

    assert record == Record(
        timestamp=datetime(2026, 10, 10, 12, 0, 0, microsecond),
        level=Level.ERROR,
        message="Disk full",
        raw=line,
    )
    assert record.timestamp.tzinfo is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("DEBUG", Level.DEBUG),
        ("info", Level.INFO),
        ("WaRnInG", Level.WARNING),
        ("ERROR", Level.ERROR),
        ("critical", Level.CRITICAL),
        ("WARN", Level.WARNING),
        ("warn", Level.WARNING),
    ],
)
def test_levels_are_case_insensitive_and_warn_is_an_alias(name, expected):
    record = parse_line(f"2026-10-10T12:00:00.123 {name} Slow")

    assert record is not None
    assert record.level is expected
    assert record.message == "Slow"


@pytest.mark.parametrize("suffix", ["", " ", "\t", "   "])
def test_message_may_be_empty(suffix):
    line = f"2026-10-10 12:00:00 INFO{suffix}"

    record = parse_line(line)

    assert record is not None
    assert record.message == ""
    assert record.raw == line


@pytest.mark.parametrize("ending", ["", "\n", "\r\n"])
def test_raw_text_and_message_are_preserved_without_line_terminator(ending):
    line = "2026-10-10 12:00:00\twArN\tcafé: disk  almost full!  "

    record = parse_line(line + ending)

    assert record is not None
    assert record.raw == line
    assert record.message == "café: disk  almost full!  "
    assert record.level is Level.WARNING


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-10T12:00:00Z INFO x",
        "2026-10-10T12:00:00+02:00 INFO x",
        "2026-10-10T12:00:00-05:00 INFO x",
        "10/10/2026 12:00:00 INFO x",
        "2026-10-10 12:00:00 NOTICE x",
        "2026-10-10 12:00:00 INFO2 x",
        "   at foo()",
        "",
        "\n",
        "   ",
        "2026-02-29 12:00:00 INFO x",
        "2026-13-10 12:00:00 INFO x",
        "2026-10-32 12:00:00 INFO x",
        "2026-10-10 24:00:00 INFO x",
        "2026-10-10 12:60:00 INFO x",
        "2026-10-10 12:00:60 INFO x",
        "2026-10-10 12:00 INFO x",
        "2026-10-10 12:00:00. INFO x",
        "2026-10-10 12:00:00",
        "2026-10-10 12:00:00INFO x",
        " 2026-10-10 12:00:00 INFO x",
    ],
)
def test_unparseable_lines_return_none(line):
    assert parse_line(line) is None


def test_valid_leap_day_is_accepted():
    record = parse_line("2024-02-29 23:59:59 DEBUG leap day")

    assert record is not None
    assert record.timestamp == datetime(2024, 2, 29, 23, 59, 59)
