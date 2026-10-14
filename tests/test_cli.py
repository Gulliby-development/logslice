"""End-to-end CLI tests using the module entry point and real UTF-8 streams."""

import importlib
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, input_text: str = "") -> subprocess.CompletedProcess[str]:
    """Run from outside the repository with an explicit source-package path."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    # A non-UTF-8 default must not override the CLI's UTF-8 stream contract.
    env["PYTHONIOENCODING"] = "ascii:strict"
    return subprocess.run(
        [sys.executable, "-m", "logslice", *args],
        input=input_text,
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT.parent,
        env=env,
        timeout=30,
        check=False,
    )


def test_project_metadata_and_console_script():
    with (ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)["project"]
    assert project["requires-python"] == ">=3.11"
    assert project.get("dependencies", []) == []
    module_name, function_name = project["scripts"]["logslice"].split(":")
    assert module_name.startswith("logslice.")
    assert callable(getattr(importlib.import_module(module_name), function_name))


def test_help_documents_inputs_options_and_accepted_forms():
    result = run_cli("--help")
    assert result.returncode == 0
    assert result.stderr == ""
    for text in (
        "--since", "--until", "--level", "--summary", "stdin", "'-'",
        "YYYY-MM-DD", "HH:MM:SS", "fraction", "DEBUG", "INFO", "WARNING",
        "WARN", "ERROR", "CRITICAL", "case-insensitive",
        "--grep", "--ignore-case", "--summary-format", "--top", "-c", "--count",
        "-m", "--max-count",
    ):
        assert text in result.stdout


def test_multiple_files_preserve_text_and_input_order(tmp_path):
    first = tmp_path / "first file.log"
    second = tmp_path / "second.log"
    first_text = "2026-10-10 12:00:00 info   first  \n"
    second_text = "2026-10-09T12:00:00.123 WARN second"
    first.write_text(first_text + "not a record\n", encoding="utf-8")
    second.write_text(second_text, encoding="utf-8")

    result = run_cli(str(first), str(second))
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == first_text + second_text + "\n"


@pytest.mark.parametrize("args", [(), ("-",)])
def test_stdin_with_no_paths_or_dash(args):
    text = (
        "2026-10-10 12:00:00 INFO ignored\n"
        "continuation line\n"
        "2026-10-10T12:00:01 ERROR retained\n"
    )
    result = run_cli(*args, "--level", "error", input_text=text)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "2026-10-10T12:00:01 ERROR retained\n"


def test_dash_is_processed_in_order_with_files(tmp_path):
    path = tmp_path / "input.log"
    file_text = "2026-10-10 12:00:00 INFO file\n"
    stdin_text = "2026-10-10 11:00:00 INFO stdin\n"
    path.write_text(file_text, encoding="utf-8")

    result = run_cli(str(path), "-", input_text=stdin_text)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == file_text + stdin_text


@pytest.mark.parametrize("unreadable_kind", ["missing", "directory"])
@pytest.mark.parametrize("after_valid_file", [False, True])
def test_unreadable_inputs_exit_two_without_traceback(
    tmp_path, unreadable_kind, after_valid_file
):
    bad_path = tmp_path / ("missing.log" if unreadable_kind == "missing" else "directory")
    if unreadable_kind == "directory":
        bad_path.mkdir()
    args = []
    expected_output = ""
    if after_valid_file:
        valid_path = tmp_path / "valid.log"
        expected_output = "2026-10-10 12:00:00 INFO readable\n"
        valid_path.write_text(expected_output, encoding="utf-8")
        args.append(str(valid_path))
    args.append(str(bad_path))

    result = run_cli(*args)
    assert result.returncode == 2
    assert (
        str(bad_path) in result.stderr or repr(str(bad_path)) in result.stderr
    )
    assert "Traceback" not in result.stderr
    assert result.stdout == expected_output


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--since", "yesterday"),
        ("--until", "10/10/2026"),
        ("--since", "2026-02-30"),
        ("--until", "2026-10-10T12:00:00Z"),
        ("--level", "BOGUS"),
    ],
)
def test_invalid_filter_values_are_usage_errors(option, value):
    result = run_cli(option, value)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr
    assert option in result.stderr
    assert value in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("level", ["warning", "WARN"])
def test_minimum_level_is_case_insensitive_and_accepts_warn(level):
    lines = [
        f"2026-10-10 12:00:00 {severity} message\n"
        for severity in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    ]
    result = run_cli("--level", level, input_text="".join(lines))
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "".join(lines[2:])


def test_time_bounds_are_inclusive_and_accept_space_and_t():
    lines = [
        f"2026-10-10 {time} ERROR message\n"
        for time in ("11:59:59", "12:00:00", "12:30:00", "13:00:00", "13:00:01")
    ]
    result = run_cli(
        "--since", "2026-10-10 12:00:00",
        "--until", "2026-10-10T13:00:00",
        input_text="".join(lines),
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "".join(lines[1:4])


def test_date_only_since_means_midnight():
    lines = [
        "2026-10-09 23:59:59 INFO before\n",
        "2026-10-10 00:00:00 INFO boundary\n",
        "2026-10-10 12:00:00 INFO after\n",
    ]
    result = run_cli("--since", "2026-10-10", input_text="".join(lines))
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "".join(lines[1:])


def test_no_matches_is_success_with_empty_stdout():
    result = run_cli(
        "--level", "critical",
        input_text="\nnot a record\n2026-10-10 12:00:00 INFO ignored\n",
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_summary_applies_all_filters_and_counts_only_unparseable_as_skipped():
    text = (
        "2026-10-09 23:59:59 ERROR before\n"
        "2026-10-10 12:00:00 INFO below minimum\n"
        "2026-10-10 12:00:00 ERROR disk full\n"
        "2026-10-10 12:01:00 CRITICAL disk full\n"
        "2026-10-10 13:00:00 ERROR network down\n"
        "2026-10-10 13:00:01 ERROR after\n"
        "not a record\n\n"
    )
    result = run_cli(
        "--summary", "--since", "2026-10-10", "--until", "2026-10-10T13:00:00",
        "--level", "error", input_text=text,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Level counts:\nDEBUG: 0\nINFO: 0\nWARNING: 0\nERROR: 2\nCRITICAL: 1\n"
        "Top 5 error messages:\n  2  disk full\n  1  network down\nSkipped lines: 2\n"
    )


def test_summary_top_five_uses_frequency_then_first_occurrence():
    messages = [("first", 2), ("second", 2), ("most", 5), ("next", 4),
                ("third", 3), ("sixth", 1), ("seventh", 1)]
    text = "".join(
        f"2026-10-10 12:00:00 ERROR {message}\n" * count
        for message, count in messages
    )
    text += "2026-10-10 12:00:00 CRITICAL fatal\n"
    text += "2026-10-10 12:00:00 INFO hello\n" * 2
    text += "invalid\n\n   at foo()\n"
    result = run_cli("--summary", input_text=text)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Level counts:\nDEBUG: 0\nINFO: 2\nWARNING: 0\nERROR: 18\nCRITICAL: 1\n"
        "Top 5 error messages:\n  5  most\n  4  next\n  3  third\n"
        "  2  first\n  2  second\nSkipped lines: 3\n"
    )


def test_summary_with_no_error_messages():
    result = run_cli("--summary", input_text="2026-10-10 12:00:00 INFO hello\n")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Level counts:\nDEBUG: 0\nINFO: 1\nWARNING: 0\nERROR: 0\nCRITICAL: 0\n"
        "Top 5 error messages:\n  (none)\nSkipped lines: 0\n"
    )


def test_crlf_utf8_and_invalid_bytes_in_file(tmp_path):
    path = tmp_path / "encoding.log"
    path.write_bytes(
        "2026-10-10 12:00:00 INFO café\r\n".encode()
        + b"2026-10-10 12:00:01 ERROR invalid \xff\r\n"
    )
    result = run_cli(str(path))
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "2026-10-10 12:00:00 INFO café\n"
        "2026-10-10 12:00:01 ERROR invalid \ufffd\n"
    )
    assert "\r" not in result.stdout


def test_stdin_and_stdout_use_utf8_despite_platform_default():
    result = run_cli(input_text="2026-10-10 12:00:00 INFO café\n")
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == "2026-10-10 12:00:00 INFO café\n"


README_LOG = (
    "2026-10-10 12:00:00 INFO Started\n"
    "2026-10-10T12:00:00.123 warn Slow response\n"
    "2026-10-10 12:01:00 ERROR Disk full\n"
)
DISK_LINE = "2026-10-10 12:01:00 ERROR Disk full\n"


def test_grep_matches_message():
    result = run_cli("--grep", "Disk", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == DISK_LINE


def test_grep_is_case_sensitive_by_default():
    result = run_cli("--grep", "disk", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stdout == ""


def test_grep_ignore_case():
    result = run_cli("--grep", "disk", "-i", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stdout == DISK_LINE


def test_grep_anchored_with_level():
    result = run_cli("--grep", "^Slow", "--level", "warning", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stdout == "2026-10-10T12:00:00.123 warn Slow response\n"


def test_grep_with_summary():
    result = run_cli("--grep", "Disk", "--summary", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "Level counts:\nDEBUG: 0\nINFO: 0\nWARNING: 0\nERROR: 1\nCRITICAL: 0\n"
        "Top 5 error messages:\n  1  Disk full\nSkipped lines: 0\n"
    )


def test_grep_invalid_pattern_exits_two():
    result = run_cli("--grep", "[", input_text=README_LOG)
    assert result.returncode == 2
    assert result.stderr.startswith("logslice: invalid --grep pattern '['")
    assert result.stdout == ""


def test_ignore_case_alone_does_not_change_output():
    plain = run_cli(input_text=README_LOG)
    with_flag = run_cli("-i", input_text=README_LOG)
    assert with_flag.returncode == plain.returncode == 0
    assert with_flag.stdout == plain.stdout == README_LOG


TEXT_SUMMARY = (
    "Level counts:\nDEBUG: 0\nINFO: 1\nWARNING: 1\nERROR: 1\nCRITICAL: 0\n"
    "Top 5 error messages:\n  1  Disk full\nSkipped lines: 0\n"
)


def test_summary_json_with_level_and_grep_filters():
    result = run_cli(
        "--summary", "--summary-format", "json",
        "--level", "warning", "--grep", "Disk", input_text=README_LOG,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.endswith("}\n")
    assert not result.stdout.endswith("\n\n")
    assert json.loads(result.stdout) == {
        "levels": {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 1, "CRITICAL": 0},
        "top_errors": [{"count": 1, "message": "Disk full"}],
        "skipped_lines": 0,
    }


def test_summary_json_unfiltered_counts_levels():
    result = run_cli("--summary", "--summary-format", "json", input_text=README_LOG)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert list(data) == ["levels", "top_errors", "skipped_lines"]
    assert data["levels"]["INFO"] == 1
    assert data["levels"]["WARNING"] == 1


@pytest.mark.parametrize("extra", [(), ("--summary-format", "text")])
def test_summary_text_is_default_and_explicit(extra):
    result = run_cli("--summary", *extra, input_text=README_LOG)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == TEXT_SUMMARY


@pytest.mark.parametrize(
    "extra",
    [(), ("/nonexistent/missing.log",), ("--grep", "[")],
)
def test_summary_format_json_requires_summary(extra):
    result = run_cli("--summary-format", "json", *extra, input_text=README_LOG)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "logslice: --summary-format requires --summary" in result.stderr


def test_summary_format_text_without_summary_is_ignored():
    result = run_cli("--summary-format", "text", input_text=README_LOG)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == README_LOG


def test_summary_format_invalid_choice_is_usage_error():
    result = run_cli("--summary", "--summary-format", "xml", input_text=README_LOG)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "usage:" in result.stderr
