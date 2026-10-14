"""Tests for count output through the logslice CLI."""

import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from logslice.cli import main

SAMPLE_LOG = (
    "2026-10-10 12:00:00 INFO Started\n"
    "2026-10-10T12:00:00.123 warn Slow response\n"
    "not a record\n"
    "2026-10-10 12:01:00 ERROR Disk full\n"
    "2026-10-10 12:02:00 ERROR Timeout\n"
)


README_LOG = (
    "2026-10-10 12:00:00 ERROR Disk full\n"
    "2026-10-10 12:00:05 ERROR Timeout\n"
    "2026-10-10 12:00:09 ERROR Disk full\n"
    "2026-10-10 12:01:00 CRITICAL Out of memory\n"
)


def write_log(tmp_path, content, name="app.log"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def run_cli(capsys, *args):
    exit_code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ((), "4\n"),
        (("--level", "warning"), "3\n"),
        (("--level", "error"), "2\n"),
        (("--level", "critical"), "0\n"),
        (("--since", "2026-10-10 12:01:00"), "2\n"),
        (("--until", "2026-10-10T12:00:00.123"), "2\n"),
        (("--grep", "Disk"), "1\n"),
        (("--grep", "disk"), "0\n"),
        (("--grep", "disk", "-i"), "1\n"),
        (("--grep", "Disk", "-v"), "3\n"),
    ],
)
def test_count_matches_filter_examples(tmp_path, capsys, filters, expected):
    path = write_log(tmp_path, SAMPLE_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, *filters, "--count")

    assert exit_code == 0
    assert stdout == expected
    assert stderr == ""


def test_count_matches_readme_errors_example(tmp_path, capsys):
    path = write_log(tmp_path, README_LOG)

    exit_code, stdout, stderr = run_cli(capsys, path, "--count")

    assert exit_code == 0
    assert stdout == "4\n"
    assert stderr == ""


def test_short_count_option_works_before_or_after_file(tmp_path, capsys):
    path = write_log(tmp_path, SAMPLE_LOG)

    before_exit, before_stdout, before_stderr = run_cli(capsys, "-c", path)
    after_exit, after_stdout, after_stderr = run_cli(capsys, path, "-c")

    assert (before_exit, before_stdout, before_stderr) == (0, "4\n", "")
    assert (after_exit, after_stdout, after_stderr) == (0, "4\n", "")


def test_count_totals_records_across_multiple_files(tmp_path, capsys):
    first = write_log(tmp_path, README_LOG, "first.log")
    second = write_log(
        tmp_path,
        "2026-10-10 12:05:00 INFO Extra record\nnot a record\n",
        "second.log",
    )

    exit_code, stdout, stderr = run_cli(capsys, "--count", first, second)

    assert exit_code == 0
    assert stdout == "5\n"
    assert stderr == ""


def test_count_reads_standard_input(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(SAMPLE_LOG))

    exit_code, stdout, stderr = run_cli(capsys, "--count")

    assert exit_code == 0
    assert stdout == "4\n"
    assert stderr == ""


def test_count_subprocess_emits_lf_bytes():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(root / "src"), env.get("PYTHONPATH")))
    )
    result = subprocess.run(
        [sys.executable, "-B", "-m", "logslice", "--count"],
        input=b"",
        capture_output=True,
        cwd=root,
        env=env,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == b"0\n"
    assert result.stderr == b""


def test_count_on_empty_file_prints_zero(tmp_path, capsys):
    path = write_log(tmp_path, "")

    exit_code, stdout, stderr = run_cli(capsys, path, "--count")

    assert exit_code == 0
    assert stdout == "0\n"
    assert stderr == ""


def test_records_still_print_without_count(tmp_path, capsys):
    contents = (
        "2026-10-10 12:00:00 INFO  Started  \n"
        "not a record\n"
        "2026-10-10T12:00:00.123 WARN Slow response"
    )
    path = write_log(tmp_path, contents)

    exit_code, stdout, stderr = run_cli(capsys, path)

    assert exit_code == 0
    assert stdout == (
        "2026-10-10 12:00:00 INFO  Started  \n"
        "2026-10-10T12:00:00.123 WARN Slow response\n"
    )
    assert stderr == ""


def test_count_conflicts_with_summary_before_grep_compilation(tmp_path, capsys):
    path = write_log(tmp_path, SAMPLE_LOG)
    invocations = [
        ("--count", "--summary"),
        ("--count", "--summary", "--top", "2"),
        ("--count", "--summary", "--grep", "["),
    ]

    for args in invocations:
        exit_code, stdout, stderr = run_cli(capsys, path, *args)
        assert exit_code == 2
        assert stdout == ""
        assert stderr == "logslice: --count conflicts with --summary\n"


def test_existing_option_errors_precede_count_summary_conflict(capsys):
    invocations = [
        (("--count", "--summary-format", "json"),
         "logslice: --summary-format requires --summary\n"),
        (("--count", "--top", "2"), "logslice: --top requires --summary\n"),
        (("--count", "--summary", "-v"),
         "logslice: --invert-match requires --grep\n"),
    ]

    for args, expected_error in invocations:
        exit_code, stdout, stderr = run_cli(capsys, *args)
        assert exit_code == 2
        assert stdout == ""
        assert stderr == expected_error


def test_unreadable_file_does_not_print_partial_count(tmp_path, capsys):
    readable = write_log(tmp_path, README_LOG, "readable.log")
    missing = tmp_path / "missing.log"

    exit_code, stdout, stderr = run_cli(capsys, "--count", readable, missing)

    assert exit_code == 2
    assert stdout == ""
    assert stderr.startswith("logslice: cannot read ")
