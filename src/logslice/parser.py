"""Parse timezone-naive log records without raising on malformed input."""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Level(IntEnum):
    """Severity order; WARN is an alias for WARNING."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    WARN = WARNING
    ERROR = 40
    CRITICAL = 50


@dataclass(frozen=True, slots=True)
class Record:
    """A parsed record with its original text, excluding the line terminator."""

    timestamp: datetime
    level: Level
    message: str
    raw: str


_LINE_RE = re.compile(
    r"(?P<timestamp>[0-9]{4}-[0-9]{2}-[0-9]{2}[ T]"
    r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?)"
    r"[ \t]+(?P<level>[A-Za-z]+)(?:[ \t]+(?P<message>.*))?"
)


def parse_line(line: str) -> Record | None:
    """Return a record, or None for invalid dates, levels, or line formats.

    Accept space or T timestamp separators and optional fractional seconds.
    Levels are case-insensitive. Timezone suffixes are not accepted.
    """
    raw = line.rstrip("\r\n")
    match = _LINE_RE.fullmatch(raw)
    if match is None:
        return None
    try:
        timestamp = datetime.fromisoformat(match["timestamp"])
        level = Level[match["level"].upper()]
    except (ValueError, KeyError):
        return None
    return Record(timestamp, level, match["message"] or "", raw)
