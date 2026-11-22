"""Plain text / markdown → chapters.

Heading heuristics: markdown '#', 'CHAPTER X', 'Part I', roman numerals,
ALL-CAPS short lines; falls back to ~4000-word splits.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..artifacts import BookMeta, Chapter

MAX_WORDS = 4000

HEADING = re.compile(
    r"^(?:"
    r"#{1,6}\s+\S"  # markdown heading
    r"|(?:(?:chapter|part|book|act|scene|section)"  # worded heading
    r"\s+(?:\d+|[ivxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten)\b[^\n]{0,55}"
    r"|(?:prologue|epilogue)(?:\s*:?[^\n]{0,55})?$)"
    r"|[IVXLC]{1,10}\.?\s*$"  # bare roman numeral
    r"|(?-i:[A-Z][A-Z '\u2019\-]{4,60}$)"  # short ALL-CAPS line (case-sensitive)
    r")",
    re.IGNORECASE,
)


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    _ = cover_dir
    text = path.read_text(errors="replace")
    meta = BookMeta(title=path.stem.replace("_", " ").title(), source_file=path.name)
    return meta, chapters_from_text(text)


def chapters_from_text(text: str) -> list[Chapter]:
    text = _normalize(text)
    headed = _split_on_headings(text)
    if len(headed) <= 1:
        headed = [("Chapter 1", text)]
    out: list[Chapter] = []
    for title, body in headed:
        body = body.strip()
        if not body:
            continue
        for i, part in enumerate(split_by_words(body, MAX_WORDS)):
            out.append(
                Chapter(
                    index=len(out),
                    title=title if i == 0 else f"{title} (cont.)",
                    text=part,
                    word_count=len(part.split()),
                    source={},
                )
            )
    if not out:
        out = [Chapter(index=0, title="Chapter 1", text="", word_count=0)]
    return out


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^[-*\s]*\* \* \*[-*\s]*$", "\n\n", text, flags=re.MULTILINE)
    return text


def _split_on_headings(text: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_title = "Front matter"
    buf: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and HEADING.match(stripped):
            if any(line.strip() for line in buf):
                chunks.append((current_title, "\n".join(buf)))
            current_title = stripped.lstrip("#").strip().title()
            buf = []
        else:
            buf.append(line)
    if any(line.strip() for line in buf):
        chunks.append((current_title, "\n".join(buf)))
    return chunks


def split_by_words(text: str, max_words: int) -> list[str]:
    """Split on paragraph boundaries, never mid-paragraph."""
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    count = 0
    for p in paragraphs:
        n = len(p.split())
        if count + n > max_words and buf:
            chunks.append("\n\n".join(buf))
            buf, count = [], 0
        buf.append(p)
        count += n
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks or [text.strip()]
