"""Tests for comma fractional seconds in log timestamps."""

from datetime import datetime

import pytest

from logslice.cli import main
from logslice.parser import Level, Record, parse_line


@pytest.mark.parametrize("separator", [" ", "T"])
def test_comma_fraction_is_read_like_a_dot(separator):
    line = f"2026-10-10{separator}12:00:00,123 ERROR Disk full"

    assert parse_line(line) == Record(
        datetime(2026, 10, 10, 12, 0, 0, 123000), Level.ERROR, "Disk full", raw=line
    )


def test_comma_and_dot_give_the_same_timestamp():
    comma_record = parse_line("2026-10-10 12:00:00,5 ERROR Disk full")
    dot_record = parse_line("2026-10-10 12:00:00.5 ERROR Disk full")

    assert comma_record is not None
    assert dot_record is not None
    assert comma_record.timestamp == dot_record.timestamp
    assert comma_record.timestamp.microsecond == 500000


@pytest.mark.parametrize(
    "line",
    [
        "2026-10-10 12:00:00, INFO x",
        "2026-10-10 12:00:00,,5 INFO x",
        "2026-10-10 12:00:00,5,6 INFO x",
        "2026-10-10,12:00:00 INFO x",
        "2026-10-10 12:00,00 INFO x",
        "2026-10-10 12:00:00,5Z INFO x",
    ],
)
def test_other_commas_are_still_rejected(line):
    assert parse_line(line) is None


def test_the_original_text_keeps_its_comma():
    line = "2026-10-10 12:00:00,123\tWARN\tSlow\r\n"

    record = parse_line(line)

    assert record is not None
    assert record.raw == "2026-10-10 12:00:00,123\tWARN\tSlow"
    assert record.level == Level.WARNING


def test_cli_filters_and_prints_comma_lines(tmp_path, capsys):
    lines = (
        "2026-10-10 12:00:00,100 INFO Started\n"
        "2026-10-10 12:00:00,900 ERROR Disk full\n"
        "2026-10-10 12:00:01,000 ERROR Timeout\n"
    )
    path = tmp_path / "app.log"
    path.write_text(lines, encoding="utf-8")

    exit_code = main([str(path), "--since", "2026-10-10 12:00:00.5", "--level", "error"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == (
        "2026-10-10 12:00:00,900 ERROR Disk full\n2026-10-10 12:00:01,000 ERROR Timeout\n"
    )
    assert captured.err == ""


def test_cli_summary_counts_comma_lines_and_skips_bad_ones(tmp_path, capsys):
    contents = (
        "2026-10-10 12:00:00,100 ERROR Disk full\n"
        "2026-10-10 12:00:00,900 ERROR Disk full\n"
        "2026-10-10 12:00:00, ERROR Broken\n"
    )
    path = tmp_path / "app.log"
    path.write_text(contents, encoding="utf-8")

    exit_code = main([str(path), "--summary"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "ERROR: 2\n" in captured.out
    assert "  2  Disk full\n" in captured.out
    assert captured.out.endswith("Skipped lines: 1\n")
    assert captured.err == ""


def test_since_and_until_still_need_a_dot(tmp_path, capsys):
    path = tmp_path / "app.log"
    path.write_text("", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        main([str(path), "--since", "2026-10-10 12:00:00,5"])
    captured = capsys.readouterr()

    assert exc_info.value.code == 2
    assert captured.out == ""
    assert (
        "argument --since: invalid datetime '2026-10-10 12:00:00,5': expected "
        "YYYY-MM-DD or YYYY-MM-DD[ T]HH:MM:SS[.fraction] without a timezone"
    ) in captured.err
