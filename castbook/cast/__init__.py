"""Cast stage — cast.json + voice library → casting.json."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..artifacts import CastFile, CastingFile, load_artifact, save_artifact
from ..config import Settings
from ..workdir import BookPaths
from .library import load_memory, save_memory
from .match import _valid_ids, _valid_voice, auto_cast


def run(
    book: BookPaths,
    cfg: Settings,
    overrides: dict[str, str] | None = None,
    speeds: dict[str, float] | None = None,
    log: Callable[[str], None] = print,
) -> Path:
    cast_file = load_artifact(CastFile, book.dir)
    if cast_file is None:
        raise FileNotFoundError(f"{book.dir}/cast.json — run `castbook analyze` first")

    backend = cfg.tts.backend
    mapping = auto_cast(
        cast_file.characters,
        book.book_id,
        memory=load_memory(cfg.data_dir),
        backend=backend,
    )
    valid = _valid_ids(backend)
    for speaker, voice_id in (overrides or {}).items():
        if Path(voice_id).exists() and Path(voice_id).suffix.lower() in {".wav", ".mp3", ".flac"}:
            log(f"[cast] voice clone {speaker} <- {voice_id} (only clone voices you may use)")
        if speaker in mapping and _valid_voice(voice_id, valid):
            mapping[speaker].voice = voice_id
        elif speaker not in mapping:
            log(f"[cast] no such speaker: {speaker!r}")
    for speaker, speed in (speeds or {}).items():
        if speaker in mapping and 0 < speed <= 2:
            mapping[speaker].speed = speed

    save_memory(
        cfg.data_dir,
        {c.name: mapping[c.id].voice for c in cast_file.characters if c.id in mapping},
    )
    save_artifact(
        CastingFile(book_id=book.book_id, map=mapping, input_hash=cast_file.input_hash),
        book.dir,
    )
    log(f"[cast] {len(mapping)} voices assigned")
    return book.dir / "casting.json"
