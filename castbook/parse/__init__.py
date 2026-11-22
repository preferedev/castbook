"""Ebook parsing → chapters.json. Dispatch on file extension."""

from __future__ import annotations

import re
from pathlib import Path

from ..artifacts import BookMeta, Chapter
from . import epub, mobi, pdf, txt

PARSERS = {
    ".epub": epub.parse,
    ".txt": txt.parse,
    ".md": txt.parse,
    ".pdf": pdf.parse,
    ".mobi": mobi.parse,
    ".azw": mobi.parse,
    ".azw3": mobi.parse,
}

# Project Gutenberg license blocks would otherwise be read aloud
_GB_START = re.compile(r"\*+\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*", re.I)
_GB_END = re.compile(r"\*+\s*END OF (?:THE|THIS) PROJECT GUTENBERG[^\n]*", re.I)


def _strip_gutenberg(chapters: list[Chapter]) -> list[Chapter]:
    out = []
    for c in chapters:
        text = c.text
        if m := _GB_START.search(text):
            text = text[m.end() :].lstrip(" *\n")
        if m := _GB_END.search(text):
            text = text[: m.start()]
        if text.strip():
            out.append(c.model_copy(update={"text": text, "word_count": len(text.split())}))
    return out


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(f"unsupported format {path.suffix!r} (supported: {supported})")
    meta, chapters = parser(path, cover_dir)
    return meta, _strip_gutenberg(chapters)
