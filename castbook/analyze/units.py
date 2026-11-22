"""Split chapter text into attribution units — shared by every attributor.

A unit is a paragraph or a quote-group; dialogue detection is by typographic
quotes, which holds for the English-language books the MVP targets.
"""

from __future__ import annotations

import re

from ..artifacts import Chapter, Unit

QUOTE_RE = re.compile("[\u201c\u0022\u2018']([^\u201d\u0022\u2019']+)[\u201d\u0022\u2019']")

MAX_UNIT_WORDS = 180


def split_units(chapter: Chapter) -> list[Unit]:
    units: list[Unit] = []
    seq = 0
    for para in _paragraphs(chapter.text):
        inside = False
        for piece in _cap(para):
            seq += 1
            after = _inside_quote(piece, inside)
            kind = "dialogue" if inside or after or QUOTE_RE.search(piece) else "narration"
            units.append(
                Unit(
                    id=f"ch{chapter.index:03d}-u{seq:04d}",
                    chapter=chapter.index,
                    text=piece,
                    speaker="",
                    kind=kind,
                )
            )
            inside = after
    return units


def _inside_quote(text: str, inside: bool = False) -> bool:
    for ch in text:
        if ch == '"':
            inside = not inside
        elif ch in "“‘":
            inside = True
        elif ch in "”’":
            inside = False
    return inside


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]


def _cap(para: str) -> list[str]:
    """Split a paragraph that exceeds the unit cap on sentence boundaries."""
    if len(para.split()) <= MAX_UNIT_WORDS:
        return [para]
    sentences = re.split(r"(?<=[.!?])\s+", para)
    out: list[str] = []
    buf: list[str] = []
    n = 0
    for s in sentences:
        w = len(s.split())
        if n + w > MAX_UNIT_WORDS and buf:
            out.append(" ".join(buf))
            buf, n = [], 0
        buf.append(s)
        n += w
    if buf:
        out.append(" ".join(buf))
    return out


def quoted_spans(text: str) -> list[str]:
    return [m.group(1).strip() for m in QUOTE_RE.finditer(text) if m.group(1).strip()]
