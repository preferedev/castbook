"""Pipeline orchestration — the single path CLI and web UI both drive."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import analyze, audio, cast, parse, tts
from .artifacts import ChaptersFile, file_hash, save_artifact
from .config import Settings
from .workdir import BookPaths, book_id_from


def import_book(src: Path, cfg: Settings, log: Callable[[str], None] = print) -> BookPaths:
    book = BookPaths(cfg.data_dir, book_id_from(src)).ensure()
    src = book.import_source(src)
    meta, chapters = parse.parse(src, cover_dir=book.source)
    save_artifact(
        ChaptersFile(
            book_id=book.book_id,
            meta=meta,
            chapters=chapters,
            input_hash=file_hash(src),
        ),
        book.dir,
    )
    log(f"[import] {meta.title} — {len(chapters)} chapters")
    return book


def analyze_book(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> Path:
    return analyze.run(book, cfg, log)


def cast_book(
    book: BookPaths,
    cfg: Settings,
    overrides: dict[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    return cast.run(book, cfg, overrides, log)


def generate_book(
    book: BookPaths,
    cfg: Settings,
    chapters: set[int] | None = None,
    log: Callable[[str], None] = print,
    speed: float = 1.0,
) -> Path:
    out = tts.run(book, cfg, log, chapters=chapters, speed=speed)
    audio.assemble_chapters(book, cfg, log)
    return out


def export_book(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> list[Path]:
    return audio.export(book, cfg, log)


def run_book(src: Path, cfg: Settings, log: Callable[[str], None] = print) -> BookPaths:
    book = import_book(src, cfg, log)
    analyze_book(book, cfg, log)
    cast_book(book, cfg, log=log)
    generate_book(book, cfg, log=log)
    export_book(book, cfg, log)
    return book
