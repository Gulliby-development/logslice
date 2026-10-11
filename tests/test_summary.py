"""Tests for the streaming summary accumulator and its rendered output."""

from datetime import datetime

import pytest

from logslice.parser import Level, Record
from logslice.summary import Summary


def make_record(level: Level, message: str = "message") -> Record:
    return Record(
        timestamp=datetime(2026, 10, 10, 12),
        level=level,
        message=message,
        raw=f"2026-10-10 12:00:00 {level.name} {message}",
    )


def test_empty_summary_renders_all_levels_and_no_messages():
    assert Summary().render() == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 0\n"
        "WARNING: 0\n"
        "ERROR: 0\n"
        "CRITICAL: 0\n"
        "Top 5 error messages:\n"
        "  (none)\n"
        "Skipped lines: 0"
    )


@pytest.mark.parametrize(
    "level", [Level.DEBUG, Level.INFO, Level.WARNING, Level.ERROR, Level.CRITICAL]
)
def test_add_counts_each_level_without_changing_other_counts(level):
    summary = Summary()
    summary.add(make_record(level))
    summary.add(make_record(level))

    assert summary.level_counts[level] == 2
    for other in Level:
        if other != level:
            assert summary.level_counts[other] == 0
    assert summary.skipped_lines == 0


def test_info_only_summary_includes_zero_error_counts_and_none():
    summary = Summary()
    summary.add(make_record(Level.INFO, "started"))
    summary.add(make_record(Level.INFO, "finished"))

    assert summary.render() == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 2\n"
        "WARNING: 0\n"
        "ERROR: 0\n"
        "CRITICAL: 0\n"
        "Top 5 error messages:\n"
        "  (none)\n"
        "Skipped lines: 0"
    )


def test_top_five_descending_counts_first_occurrence_ties_and_skipped_count():
    summary = Summary()
    # Seed in a different order from frequency and alphabetical ordering.
    frequencies = [
        ("once-first", 1),
        ("zebra-tie", 2),
        ("most", 5),
        ("alpha-tie", 2),
        ("runner-up", 4),
        ("third", 3),
        ("once-last", 1),
    ]
    for message, _ in frequencies:
        summary.add(make_record(Level.ERROR, message))
    for message, count in frequencies:
        for _ in range(count - 1):
            summary.add(make_record(Level.ERROR, message))
    summary.add(make_record(Level.CRITICAL, "critical-only"))
    summary.add(make_record(Level.INFO, "started"))
    summary.add(make_record(Level.INFO, "finished"))
    summary.skipped_lines += 3

    assert summary.render() == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 2\n"
        "WARNING: 0\n"
        "ERROR: 18\n"
        "CRITICAL: 1\n"
        "Top 5 error messages:\n"
        "  5  most\n"
        "  4  runner-up\n"
        "  3  third\n"
        "  2  zebra-tie\n"
        "  2  alpha-tie\n"
        "Skipped lines: 3"
    )


def test_error_and_critical_messages_share_counts_but_lower_levels_do_not():
    summary = Summary()
    for level in Level:
        summary.add(make_record(level, "shared message"))
    summary.add(make_record(Level.ERROR, "separate message"))

    assert summary.error_messages == {"shared message": 2, "separate message": 1}
    assert summary.render().split("Top 5 error messages:\n", 1)[1] == (
        "  2  shared message\n"
        "  1  separate message\n"
        "Skipped lines: 0"
    )


def test_tied_messages_at_top_five_boundary_keep_first_occurrence():
    summary = Summary()
    messages = ["z", "y", "x", "w", "v", "a"]
    for message in messages:
        summary.add(make_record(Level.ERROR, message))

    assert summary.render().split("Top 5 error messages:\n", 1)[1] == (
        "  1  z\n"
        "  1  y\n"
        "  1  x\n"
        "  1  w\n"
        "  1  v\n"
        "Skipped lines: 0"
    )


def test_render_does_not_consume_or_change_summary():
    summary = Summary()
    summary.add(make_record(Level.ERROR, "failure"))
    summary.skipped_lines += 1
    first = summary.render()

    assert summary.render() == first
    summary.add(make_record(Level.ERROR, "failure"))
    assert summary.level_counts[Level.ERROR] == 2
    assert summary.error_messages["failure"] == 2
    assert summary.skipped_lines == 1
    assert "  2  failure\n" in summary.render()


def test_summary_instances_do_not_share_counters():
    populated = Summary()
    empty = Summary()
    populated.add(make_record(Level.CRITICAL, "failure"))
    populated.skipped_lines += 1

    assert not empty.level_counts
    assert not empty.error_messages
    assert empty.skipped_lines == 0
