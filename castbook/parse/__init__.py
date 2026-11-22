"""Ebook parsing → chapters.json. Dispatch on file extension."""

from __future__ import annotations

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


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(f"unsupported format {path.suffix!r} (supported: {supported})")
    return parser(path, cover_dir)
