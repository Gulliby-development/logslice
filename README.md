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

Filter by message:

```sh
logslice app.log --grep Disk
```

```text
2026-10-10 12:01:00 ERROR Disk full
```

The pattern is a Python regular expression searched in the message only, not in the timestamp or level.

Drop records by message instead: add `-v` (`--invert-match`) to `--grep` to keep only the records whose message does not match.

```sh
logslice app.log --grep Disk -v
```

```text
2026-10-10 12:00:00 INFO Started
2026-10-10T12:00:00.123 warn Slow response
```

`-v` needs `--grep` (otherwise it is an error, exit status `2`) and works with `-i`, the time bounds, `--level` and `--summary`; a record with an empty message is kept unless the pattern matches the empty string.

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

JSON summary: add `--summary-format json` to print the summary as a JSON object.

```sh
logslice app.log --summary --summary-format json
```

For the three example log lines above, this prints:

```json
{
  "levels": {
    "DEBUG": 0,
    "INFO": 1,
    "WARNING": 1,
    "ERROR": 1,
    "CRITICAL": 0
  },
  "top_errors": [
    {
      "count": 1,
      "message": "Disk full"
    }
  ],
  "skipped_lines": 0
}
```

The object has the keys `levels`, `top_errors` and `skipped_lines`.

Top N: add `--top N` to `--summary` to change how many error messages are listed
(default 5, at most 100).

For example, with this `errors.log`:

```text
2026-10-10 12:00:00 ERROR Disk full
2026-10-10 12:00:05 ERROR Timeout
2026-10-10 12:00:09 ERROR Disk full
2026-10-10 12:01:00 CRITICAL Out of memory
```

`logslice errors.log --summary --top 2` prints:

```text
Level counts:
DEBUG: 0
INFO: 0
WARNING: 0
ERROR: 3
CRITICAL: 1
Top 2 error messages:
  2  Disk full
  1  Timeout
Skipped lines: 0
```

Count: add `--count` (`-c`) to print only the number of matching records, as a decimal number
and a newline, instead of the records. With the `errors.log` above, `logslice errors.log --count`
prints:

```text
4
```

and `logslice errors.log --level critical --count` prints `1`. `--count` works with the time bounds,
`--level`, `--grep`, `-i` and `-v`, adds up all input files, and prints `0` when nothing matches.
It cannot be combined with `--summary` (an error, exit status `2`). When an input file cannot be
read, no count is printed.

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
| `--grep PATTERN` | Keep only records whose message matches the Python regular expression `PATTERN` (searched in the message only). |
| `-i`, `--ignore-case` | Make `--grep` case-insensitive. |
| `-v`, `--invert-match` | With `--grep`, keep only records whose message does not match; an error without `--grep`. |
| `--summary` | Print level counts, up to the top 5 ERROR/CRITICAL messages by default, and the skipped line count instead of records. |
| `--summary-format {text,json}` | Output format of `--summary`, default `text`; `json` prints the level counts, up to the top 5 error messages by default, and the skipped line count as a JSON object. |
| `--top N` | With `--summary`, list the N most frequent ERROR/CRITICAL messages instead of 5; `N` is 1 to 100. An error without `--summary`. |
| `-c`, `--count` | Print only the number of matching records; an error with `--summary`. |
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
