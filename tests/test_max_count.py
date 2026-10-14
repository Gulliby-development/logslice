"""Tests for max-count validation and bounded CLI processing."""

import argparse
import io
import json
import sys

import pytest

from logslice.cli import main
from logslice.filters import parse_max_count

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
    "bad last\n"
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


def test_parse_max_count_accepts_inclusive_boundaries():
    assert parse_max_count("1") == 1
    assert parse_max_count("999999999") == 999999999


@pytest.mark.parametrize(
    "value",
    ["0", "01", "-1", "+1", "1.5", "abc", "", "1000000000"],
)
def test_parse_max_count_rejects_invalid_values(value):
    with pytest.raises(
        argparse.ArgumentTypeError,
        match="invalid max count",
    ) as error:
        parse_max_count(value)

    assert str(error.value) == (
        f"invalid max count {value!r}: expected an integer from 1 through 999999999"
    )


@pytest.mark.parametrize(
    "option",
    [("--max-count", "2"), ("-m", "2"), ("--max-count=2",)],
)
def test_max_count_option_spellings_print_the_first_two_matches(
    tmp_path, capsys, option
):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, *option)

    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:00 ERROR Disk full\n"
        "2026-10-10 12:00:05 ERROR Timeout\n"
    )
    assert stderr == ""


def test_max_count_option_can_precede_the_file(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, "-m", "2", path)

    assert exit_code == 0
    assert stdout.endswith("2026-10-10 12:00:05 ERROR Timeout\n")
    assert stdout.count("\n") == 2
    assert stderr == ""


def test_repeated_max_count_uses_the_last_value(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "-m", "2", "-m", "3", "--count"
    )

    assert exit_code == 0
    assert stdout == "3\n"
    assert stderr == ""


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (("--level", "critical", "--count"), "1\n"),
        (
            ("--since", "2026-10-10 12:00:01", "--grep", "Disk"),
            "2026-10-10 12:00:09 ERROR Disk full\n",
        ),
    ],
)
def test_filters_are_applied_before_counting_toward_the_limit(
    tmp_path, capsys, filters, expected
):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, *filters, "-m", "2")

    assert exit_code == 0
    assert stdout == expected
    assert stderr == ""


def test_invert_match_limits_only_accepted_records(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--grep", "Disk", "-v", "-m", "1"
    )

    assert exit_code == 0
    assert stdout == "2026-10-10 12:00:05 ERROR Timeout\n"
    assert stderr == ""


def test_count_reports_matches_through_the_limit(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)
    examples = [
        (("-m", "2"), "2\n"),
        (("--max-count", "9"), "4\n"),
        (("--max-count", "3", "--level", "critical"), "1\n"),
    ]

    for options, expected in examples:
        exit_code, stdout, stderr = run_cli(
            capsys, path, *options, "--count"
        )
        assert (exit_code, stdout, stderr) == (0, expected, "")


def test_plain_output_stops_at_limit_and_no_matches_are_successful(
    tmp_path, capsys
):
    path = write_log(tmp_path, README_LOG)
    exit_code, stdout, stderr = run_cli(capsys, path, "--max-count", "2")
    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:00 ERROR Disk full\n"
        "2026-10-10 12:00:05 ERROR Timeout\n"
    )
    assert stderr == ""

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--grep", "missing", "-m", "2", "--count"
    )
    assert (exit_code, stdout, stderr) == (0, "0\n", "")

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--grep", "missing", "-m", "2"
    )
    assert (exit_code, stdout, stderr) == (0, "", "")


def test_summary_counts_only_records_and_skipped_lines_read_before_the_stop(
    tmp_path, capsys
):
    readme = write_log(tmp_path, README_LOG)
    exit_code, stdout, stderr = run_cli(
        capsys, readme, "--max-count", "2", "--summary"
    )
    assert exit_code == 0
    assert stdout == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 0\n"
        "WARNING: 0\n"
        "ERROR: 2\n"
        "CRITICAL: 0\n"
        "Top 5 error messages:\n"
        "  1  Disk full\n"
        "  1  Timeout\n"
        "Skipped lines: 0\n"
    )
    assert stderr == ""

    mixed = write_log(tmp_path, MIXED_LOG, "mixed.log")
    limited_exit, limited_stdout, limited_stderr = run_cli(
        capsys, mixed, "-m", "2", "--summary"
    )
    full_exit, full_stdout, full_stderr = run_cli(capsys, mixed, "--summary")
    assert (limited_exit, limited_stderr) == (0, "")
    assert (full_exit, full_stderr) == (0, "")
    assert "INFO: 1\n" in limited_stdout
    assert "ERROR: 1\n" in limited_stdout
    assert limited_stdout.endswith("Skipped lines: 1\n")
    assert full_stdout.endswith("Skipped lines: 3\n")


def test_json_summary_uses_only_records_and_skipped_lines_read_before_the_stop(
    tmp_path, capsys
):
    path = write_log(tmp_path, MIXED_LOG)

    exit_code, stdout, stderr = run_cli(
        capsys,
        path,
        "--max-count=2",
        "--summary",
        "--summary-format",
        "json",
    )

    assert exit_code == 0
    assert stderr == ""
    summary = json.loads(stdout)
    assert summary["levels"] == {
        "DEBUG": 0,
        "INFO": 1,
        "WARNING": 0,
        "ERROR": 1,
        "CRITICAL": 0,
    }
    assert summary["top_errors"] == [{"count": 1, "message": "b"}]
    assert summary["skipped_lines"] == 1


def test_limit_spans_files_and_does_not_open_a_later_file(tmp_path, capsys):
    first = write_log(tmp_path, "2026-10-10 12:00:00 INFO a\n", "first.log")
    second = write_log(
        tmp_path,
        "2026-10-10 12:00:01 ERROR b\n2026-10-10 12:00:02 ERROR c\n",
        "second.log",
    )
    exit_code, stdout, stderr = run_cli(capsys, first, second, "-m", "2")
    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:00 INFO a\n"
        "2026-10-10 12:00:01 ERROR b\n"
    )
    assert stderr == ""

    missing = tmp_path / "later-missing.log"
    exit_code, stdout, stderr = run_cli(capsys, first, missing, "-m", "1")
    assert (exit_code, stdout, stderr) == (
        0,
        "2026-10-10 12:00:00 INFO a\n",
        "",
    )


def test_unreadable_file_before_limit_keeps_existing_error(tmp_path, capsys):
    missing = tmp_path / "missing.log"
    readable = write_log(tmp_path, README_LOG, "readable.log")

    exit_code, stdout, stderr = run_cli(capsys, missing, readable, "-m", "1")

    assert exit_code == 2
    assert stdout == ""
    assert stderr.startswith(f"logslice: cannot read {str(missing)!r}:")


def test_limit_stops_reading_standard_input_after_the_nth_match(capsys, monkeypatch):
    contents = (
        "bad line\n"
        "2026-10-10 12:00:00 INFO a\n"
        "2026-10-10 12:00:01 ERROR b\n"
        "bad after\n"
        "2026-10-10 12:00:02 ERROR c\n"
    )
    stream = io.StringIO(contents)
    monkeypatch.setattr(sys, "stdin", stream)

    exit_code, stdout, stderr = run_cli(capsys, "-m", "2", "--summary")

    assert exit_code == 0
    assert stdout.endswith("Skipped lines: 1\n")
    assert stream.tell() == len("bad line\n2026-10-10 12:00:00 INFO a\n2026-10-10 12:00:01 ERROR b\n")
    assert stderr == ""


@pytest.mark.parametrize(
    "value",
    ["0", "01", "-1", "+1", "1.5", "abc", "", "1000000000"],
)
def test_invalid_max_count_values_are_argparse_usage_errors(capsys, value):
    exit_code, stdout, stderr = run_argparse_cli(capsys, "-m", value)

    assert exit_code == 2
    assert stdout == ""
    assert "usage:" in stderr
    assert "logslice: error: argument -m/--max-count: invalid max count " in stderr
    assert (
        f"argument -m/--max-count: invalid max count {value!r}: expected an integer "
        "from 1 through 999999999"
    ) in stderr
    assert stderr.endswith("\n")


def test_max_count_without_a_value_keeps_argparse_missing_value_error(capsys):
    exit_code, stdout, stderr = run_argparse_cli(capsys, "-m")

    assert exit_code == 2
    assert stdout == ""
    assert "usage:" in stderr
    assert "argument -m/--max-count: expected one argument" in stderr


def test_existing_conflicts_are_checked_before_reading_with_max_count(
    tmp_path, capsys
):
    missing = tmp_path / "missing.log"
    invocations = [
        (("--count", "--summary"), "logslice: --count conflicts with --summary\n"),
        (("-v",), "logslice: --invert-match requires --grep\n"),
        (("--summary-format", "json"), "logslice: --summary-format requires --summary\n"),
        (("--top", "2"), "logslice: --top requires --summary\n"),
    ]

    for options, expected_error in invocations:
        exit_code, stdout, stderr = run_cli(
            capsys, missing, *options, "--max-count", "1"
        )
        assert (exit_code, stdout, stderr) == (2, "", expected_error)
