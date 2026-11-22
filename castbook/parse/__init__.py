"""Ebook parsing → chapters.json. Dispatch on file extension."""

from __future__ import annotations

import re
from pathlib import Path

from ..artifacts import BookMeta, Chapter
from . import docx, epub, fb2, mobi, pdf, txt

PARSERS = {
    ".epub": epub.parse,
    ".txt": txt.parse,
    ".md": txt.parse,
    ".html": txt.parse,
    ".htm": txt.parse,
    ".docx": docx.parse,
    ".fb2": fb2.parse,
    ".pdf": pdf.parse,
    ".mobi": mobi.parse,
    ".azw": mobi.parse,
    ".azw3": mobi.parse,
}

# Project Gutenberg license blocks would otherwise be read aloud. The trailing
# title is bounded and must end on '*' so a marker glued to story text (PDFs
# lose the newline) can't eat the paragraph after it.
_GB_START = re.compile(r"\*+\s*START OF (?:THE|THIS) PROJECT GUTENBERG[^*\n]{0,140}?\*+", re.I)
_GB_END = re.compile(r"\*+\s*END OF (?:THE|THIS) PROJECT GUTENBERG[^*\n]{0,140}?\*+", re.I)


def _strip_gutenberg(chapters: list[Chapter]) -> list[Chapter]:
    # In a Gutenberg file everything before the START marker / after the END
    # marker is boilerplate — including whole separate license chapters.
    start_ch = next((i for i, c in enumerate(chapters) if _GB_START.search(c.text)), 0)
    end_ch = next(
        (i for i in range(len(chapters) - 1, start_ch - 1, -1) if _GB_END.search(chapters[i].text)),
        None,
    )
    out = []
    for i, c in enumerate(chapters):
        if (start_ch is not None and i < start_ch) or (end_ch is not None and i > end_ch):
            continue
        text = c.text
        if m := _GB_START.search(text):
            text = text[m.end() :].lstrip(" *\n")
        if m := _GB_END.search(text):
            text = text[: m.start()]
        if text.strip():
            out.append(c.model_copy(update={"text": text, "word_count": len(text.split())}))
    for i, c in enumerate(out):  # indexes double as positions in export — renumber
        c.index = i
    return out


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    parser = PARSERS.get(path.suffix.lower())
    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(f"unsupported format {path.suffix!r} (supported: {supported})")
    meta, chapters = parser(path, cover_dir)
    return meta, _strip_gutenberg(chapters)
