"""Tests for datetime arguments, severity arguments, and record filtering."""

import argparse
import re
from datetime import datetime

import pytest

from logslice.filters import matches, parse_datetime, parse_level
from logslice.parser import Level, Record


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-10", datetime(2026, 10, 10)),
        ("2026-10-10 12:00:00", datetime(2026, 10, 10, 12)),
        ("2026-10-10T12:00:00", datetime(2026, 10, 10, 12)),
        ("2026-10-10 12:00:00.1", datetime(2026, 10, 10, 12, 0, 0, 100000)),
        ("2026-10-10T12:00:00.123", datetime(2026, 10, 10, 12, 0, 0, 123000)),
        ("2026-10-10T12:00:00.123456", datetime(2026, 10, 10, 12, 0, 0, 123456)),
        ("2024-02-29", datetime(2024, 2, 29)),
    ],
)
def test_parse_datetime_accepts_documented_naive_forms(value, expected):
    result = parse_datetime(value)

    assert result == expected
    assert result.tzinfo is None


@pytest.mark.parametrize(
    "value",
    [
        "",
        "yesterday",
        "10/10/2026",
        "2026-02-29",
        "2026-13-10",
        "2026-10-32",
        "2026-10-10 24:00:00",
        "2026-10-10T12:60:00",
        "2026-10-10T12:00:60",
        "2026-10-10T12:00",
        "2026-10-10T12:00:00.",
        "2026-10-10T12:00:00Z",
        "2026-10-10T12:00:00+02:00",
        "2026-10-10T12:00:00-05:00",
    ],
)
def test_parse_datetime_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError, match="invalid datetime"):
        parse_datetime(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DEBUG", Level.DEBUG),
        ("info", Level.INFO),
        ("WaRnInG", Level.WARNING),
        ("WARN", Level.WARNING),
        ("warn", Level.WARNING),
        ("error", Level.ERROR),
        ("CRITICAL", Level.CRITICAL),
    ],
)
def test_parse_level_accepts_case_insensitive_names_and_warn(value, expected):
    assert parse_level(value) is expected


@pytest.mark.parametrize("value", ["BOGUS", "NOTICE", "", "20"])
def test_parse_level_rejects_unknown_values(value):
    with pytest.raises(argparse.ArgumentTypeError, match="invalid level"):
        parse_level(value)


@pytest.mark.parametrize(
    ("option", "value"),
    [("--since", "yesterday"), ("--until", "10/10/2026"), ("--level", "BOGUS")],
)
def test_invalid_filter_arguments_produce_argparse_exit_two(option, value, capsys):
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=parse_datetime)
    parser.add_argument("--until", type=parse_datetime)
    parser.add_argument("--level", type=parse_level)

    with pytest.raises(SystemExit) as error:
        parser.parse_args([option, value])

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert option in captured.err
    assert "invalid" in captured.err
    assert value in captured.err


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (datetime(2026, 10, 10, 11, 59, 59), False),
        (datetime(2026, 10, 10, 12), True),
        (datetime(2026, 10, 10, 12, 30), True),
        (datetime(2026, 10, 10, 13), True),
        (datetime(2026, 10, 10, 13, 0, 0, 1), False),
    ],
)
def test_since_and_until_are_inclusive(timestamp, expected):
    record = Record(timestamp, Level.INFO, "message", "raw")

    assert matches(
        record,
        since=parse_datetime("2026-10-10 12:00:00"),
        until=parse_datetime("2026-10-10T13:00:00"),
    ) is expected


@pytest.mark.parametrize(
    ("timestamp", "after_since", "before_until"),
    [
        (datetime(2026, 10, 9, 23, 59, 59, 999999), False, True),
        (datetime(2026, 10, 10), True, True),
        (datetime(2026, 10, 10, 12), True, False),
    ],
)
def test_date_only_bounds_mean_midnight(timestamp, after_since, before_until):
    record = Record(timestamp, Level.INFO, "message", "raw")
    midnight = parse_datetime("2026-10-10")

    assert matches(record, since=midnight) is after_since
    assert matches(record, until=midnight) is before_until


@pytest.mark.parametrize("minimum", list(Level))
@pytest.mark.parametrize("severity", list(Level))
def test_minimum_level_uses_severity_order(minimum, severity):
    ordered_levels = [Level.DEBUG, Level.INFO, Level.WARNING, Level.ERROR, Level.CRITICAL]
    record = Record(datetime(2026, 10, 10, 12), severity, "message", "raw")
    expected = ordered_levels.index(severity) >= ordered_levels.index(minimum)

    assert matches(record, level=minimum) is expected


def test_warning_threshold_keeps_warning_error_and_critical():
    records = [
        Record(datetime(2026, 10, 10, 12), severity, "message", "raw")
        for severity in Level
    ]

    selected = [record.level for record in records if matches(record, level=parse_level("warning"))]

    assert selected == [Level.WARNING, Level.ERROR, Level.CRITICAL]


@pytest.mark.parametrize("severity", list(Level))
def test_no_filters_accepts_every_level(severity):
    record = Record(datetime(2026, 10, 10, 12), severity, "message", "raw")

    assert matches(record)


@pytest.mark.parametrize(
    ("timestamp", "severity", "expected"),
    [
        (datetime(2026, 10, 10, 11), Level.CRITICAL, False),
        (datetime(2026, 10, 10, 12, 30), Level.INFO, False),
        (datetime(2026, 10, 10, 12, 30), Level.ERROR, True),
        (datetime(2026, 10, 10, 14), Level.CRITICAL, False),
    ],
)
def test_time_and_level_filters_must_all_match(timestamp, severity, expected):
    record = Record(timestamp, severity, "message", "raw")

    assert matches(
        record,
        since=datetime(2026, 10, 10, 12),
        until=datetime(2026, 10, 10, 13),
        level=Level.WARNING,
    ) is expected


def _record(message, severity=Level.INFO, timestamp=datetime(2026, 10, 10, 12)):
    return Record(timestamp, severity, message, "raw")


def test_pattern_matches_message():
    assert matches(_record("Disk full"), pattern=re.compile("Disk")) is True


def test_pattern_without_match_rejects_record():
    assert matches(_record("Disk full"), pattern=re.compile("disk")) is False


def test_none_pattern_keeps_existing_behavior():
    assert matches(_record("Disk full"), pattern=None) is True


def test_empty_message_matches_only_patterns_matching_empty_string():
    record = _record("")

    assert matches(record, pattern=re.compile("Disk")) is False
    assert matches(record, pattern=re.compile("^$")) is True
    assert matches(record, pattern=re.compile("")) is True


def test_anchored_pattern_uses_search_on_message_start():
    pattern = re.compile("^timeout")

    assert matches(_record("timeout while reading"), pattern=pattern) is True
    assert matches(_record("read timeout"), pattern=pattern) is False


def test_case_insensitive_compiled_pattern():
    pattern = re.compile("disk", re.IGNORECASE)

    assert matches(_record("Disk full"), pattern=pattern) is True


def test_pattern_does_not_search_level_or_timestamp():
    record = _record("Started", Level.ERROR)

    assert matches(record, pattern=re.compile("ERROR")) is False
    assert matches(record, pattern=re.compile("2026")) is False


@pytest.mark.parametrize(
    ("timestamp", "severity", "message", "expected"),
    [
        (datetime(2026, 10, 10, 12, 30), Level.ERROR, "timeout", True),
        (datetime(2026, 10, 10, 12, 30), Level.ERROR, "Disk full", False),
        (datetime(2026, 10, 10, 12, 30), Level.INFO, "timeout", False),
        (datetime(2026, 10, 10, 11), Level.ERROR, "timeout", False),
        (datetime(2026, 10, 10, 14), Level.ERROR, "timeout", False),
    ],
)
def test_pattern_combines_with_level_and_time_bounds(timestamp, severity, message, expected):
    record = _record(message, severity, timestamp)

    assert matches(
        record,
        since=datetime(2026, 10, 10, 12),
        until=datetime(2026, 10, 10, 13),
        level=Level.WARNING,
        pattern=re.compile("timeout"),
    ) is expected
