"""The postmortem editor's document (PLAN phase 5): fixed sections, stored as markdown.

The editor has one field per section; the stored body is plain markdown with a `## ` heading
per section, so phase 6's grader (and anyone reading the database) sees an ordinary
document. On submit the incident's timeline, from the attempt's own trail, is appended.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Final

SECTIONS: Final = (
    ("summary", "Summary"),
    ("impact", "Impact"),
    ("cause", "Root cause"),
    ("actions", "Action items"),
)
TIMELINE_HEADING: Final = "Timeline"
MAX_SECTION_CHARS: Final = 4000

_KEYS = {title: key for key, title in SECTIONS}
_HEADING = re.compile(r"^## (.+?)\s*$", re.M)


def to_markdown(sections: Mapping[str, str], timeline: Iterable[str] = ()) -> str:
    """Sections in their fixed order (empty ones included, so the shape is stable)."""
    parts = [f"## {title}\n\n{sections.get(key, '').strip()}".rstrip() for key, title in SECTIONS]
    lines = list(timeline)
    if lines:
        parts.append(f"## {TIMELINE_HEADING}\n\n" + "\n".join(f"- {line}" for line in lines))
    return "\n\n".join(parts) + "\n"


def from_markdown(body: str) -> dict[str, str]:
    """The editor's fields back from a stored body (unknown headings are ignored)."""
    out = {key: "" for key, _ in SECTIONS}
    matches = list(_HEADING.finditer(body))
    for i, match in enumerate(matches):
        key = _KEYS.get(match.group(1))
        if key is None:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out[key] = body[match.end() : end].strip()
    return out


def clock(seconds: float) -> str:
    """`MM:SS` from the page (negative before it; under a second early reads as 00:00)."""
    sign = "-" if seconds <= -1 else ""
    whole = int(abs(seconds))
    return f"{sign}{whole // 60:02d}:{whole % 60:02d}"
