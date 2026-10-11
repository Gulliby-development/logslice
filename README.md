<p align="center"><img src="docs/logo.svg" width="96" alt="" /></p>

# logslice

Filter plain-text logs by time range and minimum severity, or summarize them, from the command line.

[![CI](https://github.com/Gulliby-development/logslice/actions/workflows/ci.yml/badge.svg)](https://github.com/Gulliby-development/logslice/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

You have a timestamped application log and want the errors from the last hour, or a quick count of
levels and the most frequent error messages, without a log server or a throwaway script.
`logslice` is a Python 3.11+ tool with no runtime dependencies that runs on Windows, macOS and Linux.

## Install

Using Python 3.11 or newer (use `python3` if that is your command):

```sh
git clone https://github.com/Gulliby-development/logslice.git
cd logslice
python -m venv .venv
```

Activate the environment on macOS/Linux:

```sh
source .venv/bin/activate
```

Or in Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then install the package:

```sh
python -m pip install .
logslice --help
```

After installation, `python -m logslice` also works.

## Usage

Accepted log lines start with a timestamp and level:

```text
2026-10-10 12:00:00 INFO Started
2026-10-10T12:00:00.123 warn Slow response
2026-10-10 12:01:00 ERROR Disk full
```

Levels are case-insensitive and ordered
`DEBUG < INFO < WARNING < ERROR < CRITICAL`; `WARN` means `WARNING`.
Messages may be empty. Timestamps are timezone-naive: `Z` and UTC offsets are not
supported. Invalid lines, including blank lines and stack-trace continuations,
are skipped.

Read one or more files in argument order:

```sh
logslice app.log worker.log
```

Filter by time and minimum level:

```sh
logslice app.log --since "2026-10-10 12:00:00" --until 2026-10-10T13:00:00 --level warning
logslice app.log --since 2026-10-10 --level ERROR
```

Both bounds are inclusive. Filter values accept `YYYY-MM-DD` (midnight) or
`YYYY-MM-DD HH:MM:SS` / `YYYY-MM-DDTHH:MM:SS`, optionally with fractional seconds.
A date-only `--until` stops at midnight, not at the end of that day.
Without `--summary`, matching records retain their original text and input order,
with one record per output line.

Read stdin with no file arguments or with `-`. On macOS/Linux:

```sh
cat app.log | logslice --level ERROR
cat app.log | logslice - --since 2026-10-10
```

In Windows PowerShell:

```powershell
Get-Content -Encoding utf8 app.log | logslice - --level ERROR
```

Summarize instead of printing records:

```sh
logslice app.log --summary
logslice app.log --since 2026-10-10 --level warning --summary
```

For the three example log lines above, `--summary` produces:

```text
Level counts:
DEBUG: 0
INFO: 1
WARNING: 1
ERROR: 1
CRITICAL: 0
Top 5 error messages:
  1  Disk full
Skipped lines: 0
```

Counts and top messages include only records passing the filters. The top list
combines ERROR and CRITICAL messages, sorts by descending frequency, and breaks
ties by first occurrence. Entries are indented by two spaces; it shows `  (none)` if there are no error messages.
The skipped count covers all unparseable input lines, not filtered-out records.

Input is processed line by line as UTF-8, replacing invalid bytes. LF and CRLF
line endings are supported; output uses UTF-8. Summary mode keeps per-level and
per-distinct-error-message counters rather than loading all records into memory.

Exit status is `0` on success, even with no matches, and `2` for invalid arguments
or unreadable files, including missing paths and directories. File errors name
the path on stderr without a traceback. Output from earlier files may already
have been written when a later file fails.

### Options

| Option | Description |
|---|---|
| `FILE ...` | Log files, read in argument order. No files or `-` reads stdin. |
| `--since DATETIME` | Inclusive lower bound: `YYYY-MM-DD` (midnight) or `YYYY-MM-DD[ T]HH:MM:SS[.fraction]`, no timezone. |
| `--until DATETIME` | Inclusive upper bound, same formats as `--since`. |
| `--level LEVEL` | Minimum level: `DEBUG`, `INFO`, `WARNING` (or `WARN`), `ERROR`, `CRITICAL`; case-insensitive (default `DEBUG`). |
| `--summary` | Print level counts, the top 5 ERROR/CRITICAL messages and the skipped line count instead of records. |
| `-h`, `--help` | Show help. |

## Development

With the virtual environment activated, install the package in editable mode and the development tools:

```sh
python -m pip install -e .
python -m pip install pytest ruff
python -m pytest -q
python -m ruff check .
```

The pytest suite covers parsing, filters, summaries and the CLI.

## License

MIT, see [LICENSE](LICENSE).

---

Built with BAKED, an open-source coding agent (bench loop round 02, BAKED ac45a9c).
