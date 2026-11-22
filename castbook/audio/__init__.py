"""Assemble + export — unit wavs → normalized chapter wavs → M4B/MP3."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import soundfile as sf

from ..artifacts import (
    AttributionFile,
    AudioManifest,
    ChapterAudio,
    ChaptersFile,
    ChapterStatus,
    Unit,
    UnitStatus,
    load_artifact,
    save_artifact,
)
from ..config import Settings
from ..tts.backend import SAMPLE_RATE
from ..workdir import BookPaths
from . import pacing
from .loudnorm import loudnorm
from .mux import export_mp3, mux_m4b


def assemble_chapters(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> Path:
    attribution = load_artifact(AttributionFile, book.dir)
    manifest = load_artifact(AudioManifest, book.dir)
    chapters = load_artifact(ChaptersFile, book.dir)
    if attribution is None or manifest is None or chapters is None:
        raise FileNotFoundError(f"{book.dir} — run earlier stages first")

    by_chapter: dict[int, list[Unit]] = {}
    for u in attribution.units:
        by_chapter.setdefault(u.chapter, []).append(u)

    wav_for = {
        uid: book.audio / e.path
        for uid, e in manifest.units.items()
        if e.status == UnitStatus.done and e.path
    }

    for index, units in sorted(by_chapter.items()):
        out = book.chapter_wav(index)
        done = manifest.chapters.get(str(index))
        if done and done.status == ChapterStatus.done and out.exists():
            stale = False
            for u in units:
                entry = manifest.units.get(u.id)
                if entry and out.stat().st_mtime < (book.audio / entry.path).stat().st_mtime:
                    stale = True
                    break
            if not stale:
                continue
        missing = [u.id for u in units if u.id not in wav_for]
        if missing:
            manifest.chapters[str(index)] = ChapterAudio(
                path="", duration_s=0.0, status=ChapterStatus.failed
            )
            log(
                f"[audio] chapter {index}: {len(missing)} units unrendered — "
                "chapter excluded from export; re-run `castbook generate`"
            )
            continue
        raw = out.with_suffix(".raw.wav")
        data = pacing.assemble(units, wav_for)
        sf.write(str(raw), data, SAMPLE_RATE)
        loudnorm(raw, out)
        raw.unlink(missing_ok=True)
        manifest.chapters[str(index)] = ChapterAudio(
            path=out.name,
            duration_s=round(len(data) / SAMPLE_RATE, 3),
            status=ChapterStatus.done,
        )
        log(f"[audio] chapter {index}: {len(data) / SAMPLE_RATE / 60:.1f} min")

    save_artifact(manifest, book.dir)
    return book.dir / "manifest.json"


def export(
    book: BookPaths,
    cfg: Settings,
    log: Callable[[str], None] = print,
    format: str | None = None,
) -> list[Path]:
    manifest = load_artifact(AudioManifest, book.dir)
    chapters = load_artifact(ChaptersFile, book.dir)
    if manifest is None or chapters is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook generate` first")

    done = sorted(
        ((int(i), c) for i, c in manifest.chapters.items() if c.status == ChapterStatus.done),
        key=lambda x: x[0],
    )
    skipped = len(manifest.chapters) - len(done)
    if skipped:
        log(f"[export] {skipped} chapters not rendered — excluded; re-run `castbook generate`")
    wavs = [book.audio / c.path for _, c in done]
    titles = [chapters.chapters[i].title for i, _ in done]

    book.export.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    fmt = format or cfg.export.format
    if fmt in ("m4b", "both"):
        out = mux_m4b(wavs, titles, chapters.meta, book.m4b(chapters.meta.title), book.dir)
        outputs.append(out)
        log(f"[export] {out.name}")
    if fmt in ("mp3", "both"):
        out = export_mp3(wavs, titles, book.export)
        outputs.append(out)
        log(f"[export] mp3 chapters → {out.name}/")
    return outputs
