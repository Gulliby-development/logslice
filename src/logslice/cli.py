"""Command-line filtering and summaries with streaming UTF-8 input."""

import argparse
import re
import sys
from contextlib import nullcontext
from typing import TextIO

from .filters import matches, parse_datetime, parse_level
from .parser import Level, parse_line
from .summary import Summary


def build_parser() -> argparse.ArgumentParser:
    """Describe the supported input formats and filters."""
    parser = argparse.ArgumentParser(
        prog="logslice",
        description="Filter plain-text logs by time and minimum severity.",
    )
    parser.add_argument(
        "files", nargs="*", metavar="FILE",
        help="files in input order; use '-' for stdin (default: stdin)",
    )
    datetime_help = (
        "YYYY-MM-DD (midnight) or YYYY-MM-DD[ T]HH:MM:SS[.fraction], "
        "without a timezone"
    )
    parser.add_argument(
        "--since", type=parse_datetime, metavar="DATETIME",
        help=f"inclusive lower timestamp bound: {datetime_help}",
    )
    parser.add_argument(
        "--until", type=parse_datetime, metavar="DATETIME",
        help=f"inclusive upper timestamp bound: {datetime_help}",
    )
    parser.add_argument(
        "--level", type=parse_level, default=Level.DEBUG, metavar="LEVEL",
        help="minimum level: DEBUG, INFO, WARNING (or WARN), ERROR, CRITICAL; "
        "case-insensitive (default: DEBUG)",
    )
    parser.add_argument(
        "--grep", metavar="PATTERN",
        help="regular expression searched in the message only "
        "(not the timestamp or level)",
    )
    parser.add_argument(
        "-i", "--ignore-case", action="store_true",
        help="make --grep case-insensitive",
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="print level counts, top 5 ERROR/CRITICAL messages, and skipped lines",
    )
    return parser


def _configure_utf8(stream: TextIO) -> None:
    """Configure real standard streams, leaving in-memory test streams alone."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; return 2 for unreadable inputs, 0 on successful processing."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        _configure_utf8(stream)
    args = build_parser().parse_args(argv)
    pattern = None
    if args.grep is not None:
        try:
            pattern = re.compile(args.grep, re.IGNORECASE if args.ignore_case else 0)
        except re.error as error:
            print(
                f"logslice: invalid --grep pattern {args.grep!r}: {error}",
                file=sys.stderr,
            )
            return 2
    summary = Summary()
    for path in args.files or ["-"]:
        try:
            with (
                nullcontext(sys.stdin)
                if path == "-"
                else open(path, encoding="utf-8", errors="replace")
            ) as lines:
                for line in lines:
                    record = parse_line(line)
                    if record is None:
                        summary.skipped_lines += 1
                        continue
                    if not matches(
                        record,
                        since=args.since,
                        until=args.until,
                        level=args.level,
                        pattern=pattern,
                    ):
                        continue
                    if args.summary:
                        summary.add(record)
                    else:
                        print(record.raw)
        except OSError as error:
            print(f"logslice: cannot read {path!r}: {error}", file=sys.stderr)
            return 2
    if args.summary:
        print(summary.render())
    return 0
