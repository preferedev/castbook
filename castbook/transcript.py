"""Speaker-labeled transcripts from unit durations — SRT/VTT per chapter, or plain text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import (
    AttributionFile,
    AudioManifest,
    CastFile,
    ChapterStatus,
    UnitStatus,
    load_artifact,
)
from .audio.pacing import pause_after
from .workdir import BookPaths


def _stamp(seconds: float, sep: str = ",") -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_transcript(
    book: BookPaths, out_dir: Path, fmt: str = "srt", speaker: str | None = None
) -> list[Path]:
    """One transcript file per rendered chapter. Returns the written paths."""
    attribution = load_artifact(AttributionFile, book.dir)
    manifest = load_artifact(AudioManifest, book.dir)
    cast = load_artifact(CastFile, book.dir)
    if attribution is None or manifest is None:
        raise ValueError("needs analyze + generate first")

    speakers = {c.id: c.name for c in cast.characters} if cast else {}
    want = None
    if speaker:
        want = next((k for k, v in speakers.items() if v.lower() == speaker.lower()), speaker)
    by_chapter: dict[int, list[Any]] = {}
    for u in attribution.units:
        by_chapter.setdefault(u.chapter, []).append(u)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for ch_index, units in sorted(by_chapter.items()):
        ch_audio = manifest.chapters.get(str(ch_index))
        if ch_audio is not None and ch_audio.status != ChapterStatus.done:
            continue
        if want is not None and not any(u.speaker == want for u in units):
            continue
        t = 0.0
        prev = None
        cues: list[tuple[float, float, str, str]] = []
        for u in units:
            entry = manifest.units.get(u.id)
            if entry is None or entry.status != UnitStatus.done:
                continue
            if prev is not None:
                t += pause_after(prev, u)
            if want is None or u.speaker == want:
                speaker_name = speakers.get(u.speaker, u.speaker)
                cues.append((t, t + entry.duration_s, speaker_name, u.text))
            t += entry.duration_s
            prev = u
        if not cues:
            continue
        if fmt == "vtt":
            body = "WEBVTT\n\n" + "\n\n".join(
                f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n<v {sp}>{tx}</v>" for a, b, sp, tx in cues
            )
            path = out_dir / f"ch{ch_index:03d}.vtt"
        elif fmt == "txt":
            body = "\n".join(f"[{sp}] {tx}" for _, _, sp, tx in cues)
            path = out_dir / f"ch{ch_index:03d}.txt"
        else:
            body = "\n\n".join(
                f"{i}\n{_stamp(a)} --> {_stamp(b)}\n[{sp}] {tx}"
                for i, (a, b, sp, tx) in enumerate(cues, 1)
            )
            path = out_dir / f"ch{ch_index:03d}.srt"
        path.write_text(body + "\n")
        written.append(path)
    return written
