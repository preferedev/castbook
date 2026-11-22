"""DOCX parsing via python-docx (optional `docx` extra)."""

from __future__ import annotations

from pathlib import Path

from ..artifacts import BookMeta, Chapter
from .txt import chapters_from_text


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    _ = cover_dir
    try:
        from docx import Document
    except ImportError:
        raise ValueError(
            "docx support needs the `docx` extra: pip install castbook[docx]"
        ) from None
    doc = Document(str(path))
    text = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    meta = BookMeta(title=path.stem.replace("_", " ").title(), source_file=path.name)
    return meta, chapters_from_text(text)
