"""Pipeline orchestration — the single path CLI and web UI both drive."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import analyze, audio, cast, parse, tts
from .artifacts import ChaptersFile, file_hash, load_artifact, save_artifact
from .config import Settings
from .workdir import BookPaths, book_id_from


def import_book(src: Path, cfg: Settings, log: Callable[[str], None] = print) -> BookPaths:
    book_id = book_id_from(src)
    src_hash = file_hash(src)
    existing = load_artifact(ChaptersFile, cfg.data_dir / book_id)
    if existing is not None and existing.input_hash != src_hash:
        n = 2
        while (cfg.data_dir / f"{book_id}-{n}").exists():
            n += 1
        log(f"[import] {book_id!r} exists with different content — importing as {book_id}-{n}")
        book_id = f"{book_id}-{n}"
    book = BookPaths(cfg.data_dir, book_id).ensure()
    src = book.import_source(src)
    meta, chapters = parse.parse(src, cover_dir=book.source)
    save_artifact(
        ChaptersFile(
            book_id=book.book_id,
            meta=meta,
            chapters=chapters,
            input_hash=src_hash,
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
    speeds: dict[str, float] | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    return cast.run(book, cfg, overrides, speeds, log)


def generate_book(
    book: BookPaths,
    cfg: Settings,
    chapters: set[int] | None = None,
    log: Callable[[str], None] = print,
    speed: float = 1.0,
    limit: int | None = None,
    workers: int = 1,
    dry_run: bool = False,
) -> Path:
    out = tts.run(
        book,
        cfg,
        log,
        chapters=chapters,
        speed=speed,
        limit=limit,
        workers=workers,
        dry_run=dry_run,
    )
    if limit is None and not dry_run:
        audio.assemble_chapters(book, cfg, log)
    return out


def export_book(
    book: BookPaths,
    cfg: Settings,
    log: Callable[[str], None] = print,
    format: str | None = None,
) -> list[Path]:
    return audio.export(book, cfg, log, format=format)


def run_book(
    src: Path,
    cfg: Settings,
    log: Callable[[str], None] = print,
    speed: float = 1.0,
) -> BookPaths:
    book = import_book(src, cfg, log)
    analyze_book(book, cfg, log)
    cast_book(book, cfg, log=log)
    generate_book(book, cfg, log=log, speed=speed)
    export_book(book, cfg, log)
    return book
