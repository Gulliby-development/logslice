"""Parse CLI filter arguments and match records against inclusive bounds."""

import argparse
import re
from datetime import datetime

from .parser import Level, Record

_DATETIME_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?)?"
)


def parse_datetime(value: str) -> datetime:
    """Parse a naive datetime; date-only values mean midnight.

    Raise ArgumentTypeError for invalid values so argparse reports exit code 2.
    Timezone suffixes and datetime forms outside the documented syntax are rejected.
    """
    if _DATETIME_RE.fullmatch(value) is not None:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError(
        f"invalid datetime {value!r}: expected YYYY-MM-DD or "
        "YYYY-MM-DD[ T]HH:MM:SS[.fraction] without a timezone"
    )


def parse_level(value: str) -> Level:
    """Parse a case-insensitive severity, accepting WARN as WARNING."""
    try:
        return Level[value.upper()]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"invalid level {value!r}: expected DEBUG, INFO, WARNING (or WARN), "
            "ERROR, or CRITICAL"
        ) from None


def parse_top(value: str) -> int:
    """Parse a top-error limit from one to 100."""
    if re.fullmatch(r"[0-9]{1,3}", value) is None:
        raise argparse.ArgumentTypeError(
            f"invalid top count {value!r}: expected an integer from 1 through 100"
        )
    count = int(value)
    if not 1 <= count <= 100:
        raise argparse.ArgumentTypeError(
            f"invalid top count {value!r}: expected an integer from 1 through 100"
        )
    return count


def parse_max_count(value: str) -> int:
    """Parse a maximum matching-record count from one to 999999999."""
    if re.fullmatch(r"[1-9][0-9]{0,8}", value) is None:
        raise argparse.ArgumentTypeError(
            f"invalid max count {value!r}: expected an integer from 1 through 999999999"
        )
    return int(value)


def matches(
    record: Record,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    level: Level = Level.DEBUG,
    pattern: re.Pattern[str] | None = None,
    invert_match: bool = False,
) -> bool:
    """Return whether a record meets both inclusive bounds and minimum severity.

    If pattern is given, it must also be found (re.search) in record.message
    only; the timestamp and level are not searched. invert_match reverses this
    pattern check and has no effect when pattern is None.

    Omitted bounds are unrestricted. A reversed range matches no records.
    Timestamps and bounds are timezone-naive, as produced by the parsers.
    """
    return (
        (since is None or record.timestamp >= since)
        and (until is None or record.timestamp <= until)
        and record.level >= level
        and (
            pattern is None
            or (pattern.search(record.message) is not None) != invert_match
        )
    )
