"""Assemble + export — unit wavs → normalized chapter wavs → M4B/MP3."""

from __future__ import annotations

import json
import shutil
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


def abs_layout(book: BookPaths, meta: object, outputs: list[Path], out_root: Path) -> Path:
    """Audiobookshelf layout: <root>/<Author>/<Title>/<Title>.m4b + cover + metadata."""
    author = _safe_dir(getattr(meta, "author", "") or "Unknown Author")
    title = _safe_dir(getattr(meta, "title", book.book_id))
    dest = out_root / author / title
    dest.mkdir(parents=True, exist_ok=True)
    for out in outputs:
        if out.is_file():
            shutil.copy2(out, dest / f"{title}{out.suffix}")
        else:
            for f in sorted(out.iterdir()):
                if f.is_file() and f.suffix.lower() in {".mp3", ".m4a"}:
                    shutil.copy2(f, dest / f.name)
    cover_path = getattr(meta, "cover_path", None)
    if cover_path:
        cover = book.dir / cover_path
        if not cover.exists():
            cover = book.source / Path(cover_path).name
        if cover.exists():
            shutil.copy2(cover, dest / "cover.jpg")
    (dest / "metadata.json").write_text(
        json.dumps(
            {
                "title": getattr(meta, "title", ""),
                "authors": [getattr(meta, "author", "")],
                "genres": ["Audiobook"],
            },
            indent=2,
        )
    )
    return dest


def _safe_dir(name: str) -> str:
    import re

    return re.sub(r'[\\/:*?"<>|]', "-", name).strip(". ") or "untitled"


def _range_label(idxs: list[int]) -> str:
    parts: list[str] = []
    i = 0
    while i < len(idxs):
        j = i
        while j + 1 < len(idxs) and idxs[j + 1] == idxs[j] + 1:
            j += 1
        parts.append(f"{idxs[i]}-{idxs[j]}" if j > i else str(idxs[i]))
        i = j + 1
    return "_".join(parts)


def export(
    book: BookPaths,
    cfg: Settings,
    log: Callable[[str], None] = print,
    format: str | None = None,
    layout: str | None = None,
    only: set[int] | None = None,
    split_hours: float | None = None,
) -> list[Path]:
    manifest = load_artifact(AudioManifest, book.dir)
    chapters = load_artifact(ChaptersFile, book.dir)
    if manifest is None or chapters is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook generate` first")

    done = sorted(
        (
            (int(i), c)
            for i, c in manifest.chapters.items()
            if c.status == ChapterStatus.done and (only is None or int(i) in only)
        ),
        key=lambda x: x[0],
    )
    if not done:
        raise FileNotFoundError(f"{book.dir} — no rendered chapters match")
    skipped = len(manifest.chapters) - len(done)
    if skipped:
        log(f"[export] {skipped} chapters not rendered or excluded; re-run `castbook generate`")
    wavs = [book.audio / c.path for _, c in done]
    titles = [chapters.chapters[i].title for i, _ in done]

    book.export.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    fmt = format or cfg.export.format
    if fmt in ("m4b", "both"):
        m4b_path = book.m4b(chapters.meta.title)
        if only is not None:
            m4b_path = m4b_path.with_name(f"{m4b_path.stem}-{_range_label(sorted(only))}.m4b")
        parts = [(wavs, titles)]
        if split_hours and split_hours > 0:
            budget = split_hours * 3600
            parts = []
            cur_w: list[Path] = []
            cur_t: list[str] = []
            acc = 0.0
            for w, t, (_, c) in zip(wavs, titles, done, strict=True):
                if cur_w and acc + c.duration_s > budget:
                    parts.append((cur_w, cur_t))
                    cur_w, cur_t, acc = [], [], 0.0
                cur_w.append(w)
                cur_t.append(t)
                acc += c.duration_s
            if cur_w:
                parts.append((cur_w, cur_t))
        for pi, (pw, pt) in enumerate(parts):
            p_out = m4b_path
            p_meta = chapters.meta
            if len(parts) > 1:
                p_out = m4b_path.with_name(f"{m4b_path.stem}-part{pi + 1}.m4b")
                p_meta = chapters.meta.model_copy(
                    update={"title": f"{chapters.meta.title} (part {pi + 1}/{len(parts)})"}
                )
            out = mux_m4b(pw, pt, p_meta, p_out, book.dir)
            outputs.append(out)
            log(f"[export] {out.name}")
    label = _range_label(sorted(only)) if only is not None else ""
    if fmt in ("mp3", "both"):
        mp3_dir = book.export
        if label:
            mp3_dir = book.export / f"{_safe_dir(getattr(chapters.meta, 'title', 'book'))}-{label}"
        out = export_mp3(wavs, titles, mp3_dir)
        outputs.append(out)
        log(f"[export] mp3 chapters → {out.name}/")
    if layout == "abs":
        abs_root = book.export / (f"abs-{label}" if label else "abs")
        dest = abs_layout(book, chapters.meta, outputs, abs_root)
        zip_path = shutil.make_archive(
            str(
                book.export
                / (
                    f"{_safe_dir(getattr(chapters.meta, 'title', 'book'))}-abs"
                    + (f"-{_range_label(sorted(only))}" if only is not None else "")
                )
            ),
            "zip",
            dest.parent,
        )
        out_zip = Path(zip_path)
        outputs.append(out_zip)
        log(f"[export] audiobookshelf → {dest} ({out_zip.name})")
    return outputs
