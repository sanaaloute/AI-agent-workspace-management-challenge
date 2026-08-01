"""Small helpers: date parsing, line chunking, workspace reset."""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Iterator, Optional, Sequence

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

# Supported date spellings: 2025-03-02, 2025/03/02, 2 March 2025, March 2, 2025
_PATTERNS = [
    re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"),
    re.compile(r"\b(\d{4})/(\d{1,2})/(\d{1,2})\b"),
    re.compile(
        r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE
    ),
    re.compile(
        r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE
    ),
]


def extract_date_from_content(content: str) -> Optional[date]:
    """Return the earliest-mentioned date found in `content`, or None.

    "Earliest-mentioned" = the first date a reader encounters scanning the
    text top to bottom, which in practice is the date a file states about
    itself (header / frontmatter) rather than dates referenced later.
    """
    best: tuple[int, date] | None = None
    for pattern in _PATTERNS:
        for m in pattern.finditer(content):
            groups = m.groups()
            try:
                if pattern is _PATTERNS[0] or pattern is _PATTERNS[1]:
                    d = date(int(groups[0]), int(groups[1]), int(groups[2]))
                elif pattern is _PATTERNS[2]:
                    d = date(int(groups[2]), _MONTHS[groups[1].lower()], int(groups[0]))
                else:
                    d = date(int(groups[2]), _MONTHS[groups[0].lower()], int(groups[1]))
            except ValueError:
                continue  # e.g. 2025-13-40 is not a date
            if best is None or m.start() < best[0]:
                best = (m.start(), d)
    return best[1] if best else None


def month_key(d: date) -> str:
    """'2025-03' style grouping key for a date."""
    return f"{d.year:04d}-{d.month:02d}"


def chunk_lines(lines: Sequence[str], size: int) -> Iterator[list[str]]:
    """Yield `lines` in chunks of at most `size`."""
    for i in range(0, len(lines), size):
        yield list(lines[i : i + size])


def reset_workspace(workspace: str | Path, original: str | Path) -> None:
    """Rebuild `workspace` as a pristine copy of `original`.

    Clears the workspace's *contents* rather than the directory itself:
    under Docker the workspace is typically a bind mount, and removing the
    mount point fails with "Device or resource busy".
    """
    workspace = Path(workspace)
    original = Path(original)
    if not original.is_dir():
        raise FileNotFoundError(f"original workspace not found: {original}")
    workspace.mkdir(parents=True, exist_ok=True)
    for child in workspace.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.copytree(original, workspace, dirs_exist_ok=True)
