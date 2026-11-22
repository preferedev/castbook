"""Speaker-labeled transcripts from unit durations — SRT/VTT per chapter, or plain text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import AttributionFile, AudioManifest, CastFile, load_artifact
from .workdir import BookPaths


def _stamp(seconds: float, sep: str = ",") -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_transcript(book: BookPaths, out_dir: Path, fmt: str = "srt") -> list[Path]:
    """One transcript file per rendered chapter. Returns the written paths."""
    attribution = load_artifact(AttributionFile, book.dir)
    manifest = load_artifact(AudioManifest, book.dir)
    cast = load_artifact(CastFile, book.dir)
    if attribution is None or manifest is None:
        raise ValueError("needs analyze + generate first")

    speakers = {c.id: c.name for c in cast.characters} if cast else {}
    by_chapter: dict[int, list[Any]] = {}
    for u in attribution.units:
        by_chapter.setdefault(u.chapter, []).append(u)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for ch_index, units in sorted(by_chapter.items()):
        t = 0.0
        cues: list[tuple[float, float, str, str]] = []
        for u in units:
            entry = manifest.units.get(u.id)
            dur = entry.duration_s if entry else 0.0
            if entry is None:
                continue
            speaker = speakers.get(u.speaker, u.speaker)
            cues.append((t, t + dur, speaker, u.text))
            t += dur
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
