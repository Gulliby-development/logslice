"""Tests for inverted message matching through the filter and CLI."""

import json
import re
from datetime import datetime

import pytest

from logslice.cli import main
from logslice.filters import matches
from logslice.parser import Level, Record

LOG_CONTENT = (
    "2026-10-10 12:00:00 INFO Started\n"
    "2026-10-10T12:00:00.123 warn Slow response\n"
    "2026-10-10 12:01:00 ERROR Disk full\n"
    "2026-10-10 12:02:00 ERROR\n"
    "not a log line\n"
    "2026-10-10 12:03:00 error disk quota\n"
)


def write_log(tmp_path):
    path = tmp_path / "app.log"
    path.write_text(LOG_CONTENT, encoding="utf-8")
    return path


def run_cli(capsys, *args):
    exit_code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_matches_inverts_pattern_result_and_ignores_inversion_without_pattern():
    pattern = re.compile("Disk")
    matching = Record(datetime(2026, 10, 10), Level.INFO, "Disk full", "raw")
    nonmatching = Record(datetime(2026, 10, 10), Level.INFO, "Started", "raw")

    assert matches(matching, pattern=pattern, invert_match=True) is False
    assert matches(nonmatching, pattern=pattern, invert_match=True) is True
    assert matches(nonmatching, invert_match=True) is True


@pytest.mark.parametrize(
    "option",
    ["-v", "--invert-match"],
)
def test_invert_match_keeps_records_without_pattern_match(tmp_path, capsys, option):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "--grep", "Disk", option)

    assert exit_code == 0
    assert stderr == ""
    assert stdout == (
        "2026-10-10 12:00:00 INFO Started\n"
        "2026-10-10T12:00:00.123 warn Slow response\n"
        "2026-10-10 12:02:00 ERROR\n"
        "2026-10-10 12:03:00 error disk quota\n"
    )


@pytest.mark.parametrize(
    "args",
    [
        ("--grep", "disk", "-i", "-v"),
        ("-vi", "--grep", "disk"),
    ],
)
def test_case_insensitive_inversion_supports_combined_short_flags(
    tmp_path, capsys, args
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, *args)

    assert exit_code == 0
    assert stderr == ""
    assert stdout == (
        "2026-10-10 12:00:00 INFO Started\n"
        "2026-10-10T12:00:00.123 warn Slow response\n"
        "2026-10-10 12:02:00 ERROR\n"
    )


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (".", "2026-10-10 12:02:00 ERROR\n"),
        (
            "^$",
            (
                "2026-10-10 12:00:00 INFO Started\n"
                "2026-10-10T12:00:00.123 warn Slow response\n"
                "2026-10-10 12:01:00 ERROR Disk full\n"
                "2026-10-10 12:03:00 error disk quota\n"
            ),
        ),
    ],
)
def test_inversion_uses_regex_semantics_for_empty_messages(
    tmp_path, capsys, pattern, expected
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "--grep", pattern, "-v")

    assert exit_code == 0
    assert stderr == ""
    assert stdout == expected


@pytest.mark.parametrize(
    "filters",
    [
        ("--level", "error", "--grep", "Disk"),
        ("--grep", "Disk", "--since", "2026-10-10T12:00:01"),
    ],
)
def test_inversion_remains_conjunctive_with_other_filters(
    tmp_path, capsys, filters
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "-v", *filters)

    assert exit_code == 0
    assert stderr == ""
    assert stdout == (
        "2026-10-10 12:02:00 ERROR\n"
        "2026-10-10 12:03:00 error disk quota\n"
    )


def test_text_summary_counts_only_retained_records_and_skipped_lines(tmp_path, capsys):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "-v", "--grep", "Disk", "--summary"
    )

    assert exit_code == 0
    assert stderr == ""
    assert stdout == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 1\n"
        "WARNING: 1\n"
        "ERROR: 2\n"
        "CRITICAL: 0\n"
        "Top 5 error messages:\n"
        "  1  \n"
        "  1  disk quota\n"
        "Skipped lines: 1\n"
    )


def test_json_summary_counts_only_retained_records_and_skipped_lines(
    tmp_path, capsys
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "-v", "--grep", "Disk", "--summary", "--summary-format", "json"
    )

    assert exit_code == 0
    assert stderr == ""
    summary = json.loads(stdout)
    assert summary["levels"]["ERROR"] == 2
    assert summary["top_errors"] == [
        {"count": 1, "message": ""},
        {"count": 1, "message": "disk quota"},
    ]
    assert summary["skipped_lines"] == 1


@pytest.mark.parametrize("missing", [False, True])
def test_invert_match_without_grep_fails_before_reading_input(
    tmp_path, capsys, missing
):
    path = tmp_path / "missing.log" if missing else write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "-v")

    assert exit_code == 2
    assert stdout == ""
    assert stderr == "logslice: --invert-match requires --grep\n"


def test_summary_format_validation_precedes_invert_match_validation(
    tmp_path, capsys
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "-v", "--summary-format", "json"
    )

    assert exit_code == 2
    assert stdout == ""
    assert stderr == "logslice: --summary-format requires --summary\n"


def test_invalid_grep_pattern_is_checked_after_invert_validation(tmp_path, capsys):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "-v", "--grep", "(")

    assert exit_code == 2
    assert stdout == ""
    assert stderr.startswith("logslice: invalid --grep pattern '('")
    assert stderr.count("\n") == 1


def test_grep_without_value_keeps_argparse_missing_value_error(tmp_path, capsys):
    path = write_log(tmp_path)

    with pytest.raises(SystemExit) as error:
        main([str(path), "--grep", "-v"])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "argument --grep: expected one argument" in captured.err
