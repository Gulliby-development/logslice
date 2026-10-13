"""Tests for configurable top-error summaries through the CLI."""

import json

import pytest

from logslice.cli import main

LOG_CONTENT = (
    "2026-10-10 12:00:00 ERROR Disk full\n"
    "2026-10-10 12:00:05 ERROR Timeout\n"
    "2026-10-10 12:00:09 ERROR Disk full\n"
    "2026-10-10 12:01:00 CRITICAL Out of memory\n"
)


def write_log(tmp_path, content=LOG_CONTENT):
    path = tmp_path / "app.log"
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


def test_top_two_text_summary_matches_worked_example(tmp_path, capsys):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "--summary", "--top", "2")

    assert exit_code == 0
    assert stderr == ""
    assert stdout == (
        "Level counts:\n"
        "DEBUG: 0\n"
        "INFO: 0\n"
        "WARNING: 0\n"
        "ERROR: 3\n"
        "CRITICAL: 1\n"
        "Top 2 error messages:\n"
        "  2  Disk full\n"
        "  1  Timeout\n"
        "Skipped lines: 0\n"
    )


def test_top_limits_json_summary_without_changing_keys_or_counts(tmp_path, capsys):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--summary", "--top", "1", "--summary-format", "json"
    )

    assert exit_code == 0
    assert stderr == ""
    summary = json.loads(stdout)
    assert list(summary) == ["levels", "top_errors", "skipped_lines"]
    assert summary["levels"]["ERROR"] == 3
    assert summary["levels"]["CRITICAL"] == 1
    assert summary["top_errors"] == [{"count": 2, "message": "Disk full"}]
    assert summary["skipped_lines"] == 0


@pytest.mark.parametrize(
    ("top_args", "expected_header", "expected_entries"),
    [
        (("--top", "1"), "Top 1 error messages:\n", "  2  Disk full\n"),
        (
            ("--top=2",),
            "Top 2 error messages:\n",
            "  2  Disk full\n  1  Timeout\n",
        ),
        (
            ("--top", "07"),
            "Top 7 error messages:\n",
            "  2  Disk full\n  1  Timeout\n  1  Out of memory\n",
        ),
        (
            ("--top", "100"),
            "Top 100 error messages:\n",
            "  2  Disk full\n  1  Timeout\n  1  Out of memory\n",
        ),
    ],
)
def test_top_accepts_valid_values_and_normalizes_the_header(
    tmp_path, capsys, top_args, expected_header, expected_entries
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(capsys, path, "--summary", *top_args)

    assert exit_code == 0
    assert stderr == ""
    assert expected_header in stdout
    assert expected_entries in stdout


@pytest.mark.parametrize(
    "value",
    ["0", "101", "1000", "-3", "+5", " 5", "5 ", "1e1", "x", "٣", ""],
)
def test_invalid_top_values_are_argparse_usage_errors(capsys, value):
    exit_code, stdout, stderr = run_argparse_cli(
        capsys, "--summary", "--top", value
    )

    assert exit_code == 2
    assert stdout == ""
    assert stderr.rstrip().endswith(
        "argument --top: invalid top count "
        f"{value!r}: expected an integer from 1 through 100"
    )
    assert "Traceback" not in stderr


def test_top_without_value_keeps_argparse_missing_value_error(capsys):
    exit_code, stdout, stderr = run_argparse_cli(capsys, "--summary", "--top")

    assert exit_code == 2
    assert stdout == ""
    assert "argument --top: expected one argument" in stderr


def test_top_without_summary_fails_before_reading_input(tmp_path, capsys):
    missing_path = tmp_path / "missing.log"

    exit_code, stdout, stderr = run_cli(capsys, missing_path, "--top", "5")

    assert exit_code == 2
    assert stdout == ""
    assert stderr == "logslice: --top requires --summary\n"


def test_summary_format_validation_precedes_top_validation(capsys):
    exit_code, stdout, stderr = run_cli(
        capsys, "--top", "5", "--summary-format", "json"
    )

    assert exit_code == 2
    assert stdout == ""
    assert stderr == "logslice: --summary-format requires --summary\n"


def test_top_validation_precedes_invert_match_validation(capsys):
    exit_code, stdout, stderr = run_cli(capsys, "--top", "2", "-v")

    assert exit_code == 2
    assert stdout == ""
    assert stderr == "logslice: --top requires --summary\n"


def test_repeated_top_uses_last_value(tmp_path, capsys):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--summary", "--top", "1", "--top", "2"
    )

    assert exit_code == 0
    assert stderr == ""
    assert "Top 2 error messages:\n" in stdout
    assert "  1  Timeout\n" in stdout


def test_top_with_fewer_distinct_errors_lists_only_available_messages(tmp_path, capsys):
    path = write_log(
        tmp_path,
        "2026-10-10 12:00:00 ERROR Disk full\n"
        "2026-10-10 12:00:01 ERROR Disk full\n",
    )

    exit_code, stdout, stderr = run_cli(capsys, path, "--summary", "--top", "100")

    assert exit_code == 0
    assert stderr == ""
    assert "Top 100 error messages:\n  2  Disk full\n" in stdout
    assert "  (none)" not in stdout


def test_top_with_no_error_messages_keeps_none_marker(tmp_path, capsys):
    path = write_log(
        tmp_path, "2026-10-10 12:00:00 INFO Started\n"
    )

    exit_code, stdout, stderr = run_cli(capsys, path, "--summary", "--top", "3")

    assert exit_code == 0
    assert stderr == ""
    assert "Top 3 error messages:\n  (none)\n" in stdout


@pytest.mark.parametrize(
    ("filters", "expected_entries"),
    [
        (("--level", "critical"), "  1  Out of memory\n"),
        (("--grep", "Disk"), "  2  Disk full\n"),
        (("--grep", "Disk", "-v"), "  1  Timeout\n  1  Out of memory\n"),
    ],
)
def test_top_preserves_level_and_grep_filter_interactions(
    tmp_path, capsys, filters, expected_entries
):
    path = write_log(tmp_path)

    exit_code, stdout, stderr = run_cli(
        capsys, path, "--summary", "--top", "3", *filters
    )

    assert exit_code == 0
    assert stderr == ""
    assert expected_entries in stdout
