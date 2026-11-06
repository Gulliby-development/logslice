"""Tests for skipping leading matching records with --offset."""

import argparse
import json

import pytest

from logslice.cli import main
from logslice.filters import parse_offset

README_LOG = (
    "2026-10-10 12:00:00 ERROR Disk full\n"
    "2026-10-10 12:00:05 ERROR Timeout\n"
    "2026-10-10 12:00:09 ERROR Disk full\n"
    "2026-10-10 12:01:00 CRITICAL Out of memory\n"
)
MIXED_LOG = (
    "2026-10-10 12:00:00 INFO a\n"
    "bad line\n"
    "2026-10-10 12:00:01 ERROR b\n"
    "bad again\n"
    "2026-10-10 12:00:02 ERROR c\n"
)


def write_log(tmp_path, content, name="app.log"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def run_cli(capsys, *args):
    exit_code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def run_argparse_cli(capsys, *args):
    with pytest.raises(SystemExit) as error:
        main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return error.value.code, captured.out, captured.err


def test_parse_offset_accepts_inclusive_boundaries():
    assert parse_offset("0") == 0
    assert parse_offset("7") == 7
    assert parse_offset("999999999") == 999999999


@pytest.mark.parametrize(
    "value",
    ["00", "01", "-1", "+1", "1.5", "abc", "", "1000000000"],
)
def test_parse_offset_rejects_invalid_values(value):
    with pytest.raises(argparse.ArgumentTypeError, match="invalid offset"):
        parse_offset(value)


def test_offset_three_matches_the_readme_example(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, "--offset", "3")

    assert exit_code == 0
    assert stderr == ""
    assert stdout == "2026-10-10 12:01:00 CRITICAL Out of memory\n"


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        ("0", README_LOG),
        ("1", README_LOG.split("\n", 1)[1]),
        ("4", ""),
        ("9", ""),
    ],
)
def test_offset_skips_the_first_matching_records(tmp_path, capsys, offset, expected):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, "--offset", offset)

    assert (exit_code, stdout, stderr) == (0, expected, "")


def test_offset_counts_records_after_the_filters(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, _ = run_cli(capsys, path, "--grep", "Disk", "--offset", "1")

    assert exit_code == 0
    assert stdout == "2026-10-10 12:00:09 ERROR Disk full\n"


def test_offset_counts_across_files_in_argument_order(tmp_path, capsys):
    first = write_log(tmp_path, README_LOG, "first.log")
    second = write_log(tmp_path, MIXED_LOG, "second.log")

    exit_code, stdout, _ = run_cli(capsys, first, second, "--offset", "5")

    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:01 ERROR b\n"
        "2026-10-10 12:00:02 ERROR c\n"
    )


def test_offset_with_max_count_limits_after_the_skipped_records(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, _ = run_cli(capsys, path, "--offset", "1", "--max-count", "2")

    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:05 ERROR Timeout\n"
        "2026-10-10 12:00:09 ERROR Disk full\n"
    )


@pytest.mark.parametrize(
    ("offset", "expected"),
    [("0", "4\n"), ("1", "3\n"), ("4", "0\n"), ("6", "0\n")],
)
def test_offset_with_count_prints_the_remaining_number(tmp_path, capsys, offset, expected):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, _ = run_cli(capsys, path, "--offset", offset, "--count")

    assert (exit_code, stdout) == (0, expected)


def test_offset_with_summary_summarizes_only_the_kept_records(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, _ = run_cli(
        capsys, path, "--offset", "2", "--summary", "--summary-format", "json"
    )

    assert exit_code == 0
    assert json.loads(stdout) == {
        "levels": {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 1, "CRITICAL": 1},
        "top_errors": [
            {"count": 1, "message": "Disk full"},
            {"count": 1, "message": "Out of memory"},
        ],
        "skipped_lines": 0,
    }


def test_offset_leaves_the_skipped_line_count_alone(tmp_path, capsys):
    path = write_log(tmp_path, MIXED_LOG)

    exit_code, stdout, _ = run_cli(capsys, path, "--offset", "2", "--summary")

    assert exit_code == 0
    assert stdout.endswith("Skipped lines: 2\n")


def test_repeated_offset_takes_the_last_value(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, _ = run_cli(capsys, path, "--offset", "9", "--offset", "3")

    assert exit_code == 0
    assert stdout == "2026-10-10 12:01:00 CRITICAL Out of memory\n"


@pytest.mark.parametrize("value", ["-1", "01", "x", "1000000000"])
def test_invalid_offset_is_an_argparse_error(tmp_path, capsys, value):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_argparse_cli(capsys, path, "--offset", value)

    assert exit_code == 2
    assert stdout == ""
    assert f"argument --offset: invalid offset {value!r}: expected an integer from 0 through 999999999" in stderr
