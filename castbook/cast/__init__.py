"""Cast stage — cast.json + voice library → casting.json."""

from __future__ import annotations

from pathlib import Path

from ..artifacts import CastFile, CastingFile, load_artifact, save_artifact
from ..config import Settings
from ..workdir import BookPaths
from .match import auto_cast


def run(book: BookPaths, cfg: Settings, overrides: dict[str, str] | None = None, log=print) -> Path:
    cast_file = load_artifact(CastFile, book.dir)
    if cast_file is None:
        raise FileNotFoundError(f"{book.dir}/cast.json — run `castbook analyze` first")

    mapping = auto_cast(cast_file.characters, book.book_id)
    for speaker, voice_id in (overrides or {}).items():
        if speaker in mapping:
            mapping[speaker].voice = voice_id

    save_artifact(
        CastingFile(book_id=book.book_id, map=mapping, input_hash=cast_file.input_hash),
        book.dir,
    )
    log(f"[cast] {len(mapping)} voices assigned")
    return book.dir / "casting.json"
