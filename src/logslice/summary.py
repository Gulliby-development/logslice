"""Accumulate filtered records without retaining the input lines."""

import json
from collections import Counter
from dataclasses import dataclass, field

from .parser import Level, Record


@dataclass
class Summary:
    """Count levels and distinct error messages; ties keep first-seen order."""

    level_counts: Counter[Level] = field(default_factory=Counter)
    error_messages: Counter[str] = field(default_factory=Counter)
    skipped_lines: int = 0

    def add(self, record: Record) -> None:
        """Include one record that has passed the filters."""
        self.level_counts[record.level] += 1
        if record.level >= Level.ERROR:
            self.error_messages[record.message] += 1

    def render(self, top: int = 5) -> str:
        """Return all levels, up to top error messages, and skipped count."""
        lines = ["Level counts:"]
        lines.extend(f"{level.name}: {self.level_counts[level]}" for level in Level)
        lines.append(f"Top {top} error messages:")
        top_messages = self.error_messages.most_common(top)
        if top_messages:
            lines.extend(
                f"  {count}  {message}" for message, count in top_messages
            )
        else:
            lines.append("  (none)")
        lines.append(f"Skipped lines: {self.skipped_lines}")
        return "\n".join(lines)

    def render_json(self, top: int = 5) -> str:
        """Return level counts, up to top error messages, and skipped count as JSON."""
        payload = {
            "levels": {level.name: self.level_counts[level] for level in Level},
            "top_errors": [
                {"count": count, "message": message}
                for message, count in self.error_messages.most_common(top)
            ],
            "skipped_lines": self.skipped_lines,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
