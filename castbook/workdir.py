"""Book workdir layout — the only module that knows where artifacts live."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

SLUG_RE = re.compile(r"[^a-z0-9]+")


def book_id_from(path: Path, title: str | None = None) -> str:
    base = SLUG_RE.sub("-", (title or path.stem).lower()).strip("-")
    return base[:60] or "book"


class BookPaths:
    """books/<id>/ — every artifact path in one place."""

    def __init__(self, root: Path, book_id: str) -> None:
        self.root = root
        self.book_id = book_id
        self.dir = root / book_id
        self.source = self.dir / "source"
        self.audio = self.dir / "audio"
        self.export = self.dir / "export"
        self.project_file = self.dir / "book.castbook.json"

    def ensure(self) -> BookPaths:
        for d in (self.dir, self.source, self.audio, self.export):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def unit_wav(self, unit_id: str) -> Path:
        return self.audio / f"{unit_id}.wav"

    def chapter_wav(self, index: int) -> Path:
        return self.audio / f"ch{index:03d}.wav"

    def m4b(self, title: str) -> Path:
        return self.export / f"{book_id_from(Path(title), title)}.m4b"

    def import_source(self, src: Path) -> Path:
        self.ensure()
        dst = self.source / src.name
        if src.resolve() != dst.resolve():
            shutil.copyfile(src, dst)
        return dst

    def exists(self, name: str) -> Path:
        return self.dir / f"{name}.json"
