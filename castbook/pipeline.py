"""Pipeline orchestration — the single path CLI and web UI both drive."""

from __future__ import annotations

import threading
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
    meta, chapters = parse.parse(src, cover_dir=book.dir)
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


_COVER_MAGIC = ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"RIFF", ".webp"))


def set_cover(book: BookPaths, image: Path) -> str:
    """Replace the book's cover art (png/jpg/webp, sniffed by magic bytes)."""
    head = image.read_bytes()[:16]
    ext = next((e for sig, e in _COVER_MAGIC if head.startswith(sig)), None)
    if ext == ".webp" and head[8:12] != b"WEBP":
        ext = None
    if ext is None:
        raise ValueError("not a png/jpg/webp image")
    for old in book.dir.glob("cover.*"):
        old.unlink()
    dest = book.dir / f"cover{ext}"
    dest.write_bytes(image.read_bytes())
    chapters = load_artifact(ChaptersFile, book.dir)
    if chapters is not None:
        chapters.meta.cover_path = dest.name
        save_artifact(chapters, book.dir)
    return dest.name


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
    cancel: threading.Event | None = None,
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
        cancel=cancel,
    )
    if limit is None and not dry_run:
        audio.assemble_chapters(book, cfg, log)
    return out


def export_book(
    book: BookPaths,
    cfg: Settings,
    log: Callable[[str], None] = print,
    format: str | None = None,
    layout: str | None = None,
    only: set[int] | None = None,
) -> list[Path]:
    return audio.export(book, cfg, log, format=format, layout=layout, only=only)


def run_book(
    src: Path,
    cfg: Settings,
    log: Callable[[str], None] = print,
    speed: float = 1.0,
    workers: int = 1,
    layout: str | None = None,
) -> BookPaths:
    book = import_book(src, cfg, log)
    analyze_book(book, cfg, log)
    cast_book(book, cfg, log=log)
    generate_book(book, cfg, log=log, speed=speed, workers=workers)
    export_book(book, cfg, log, layout=layout)
    return book
