"""PDF parsing — text-layer extraction via pdfminer, then heading-aware
chapter splitting shared with the TXT parser. Scanned (image-only) PDFs
extract to near-empty text and fail loudly at the boundary."""

from __future__ import annotations

import re
from pathlib import Path

from ..artifacts import BookMeta, Chapter
from .txt import chapters_from_text

_MIN_TEXT_CHARS = 200


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    from pdfminer.high_level import extract_text  # deferred: heavy import
    from pdfminer.pdfparser import PDFSyntaxError

    try:
        text = extract_text(str(path))
    except PDFSyntaxError as e:
        raise ValueError(f"not a parseable PDF: {e}") from e
    text = _clean(text)
    if len(text) < _MIN_TEXT_CHARS:
        raise ValueError(
            f"{path.name}: extracted {len(text)} chars — scanned/image-only PDFs "
            "need OCR first (not supported)"
        )
    meta = BookMeta(
        title=path.stem.replace("_", " ").replace("-", " ").title(),
        author="Unknown",
        source_file=path.name,
    )
    return meta, chapters_from_text(text)


def _clean(text: str) -> str:
    # pdfminer emits form feeds between pages and hyphen-newline wraps
    text = text.replace("\x0c", "\n\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return text
