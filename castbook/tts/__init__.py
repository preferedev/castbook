"""Synthesize stage — attribution + casting → per-unit wavs + manifest.

Resume rule: a unit re-renders only when its rendered hash (text + resolved
VoiceSpec) differs from the manifest entry, or its wav is missing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..artifacts import (
    AttributionFile,
    AudioEntry,
    AudioManifest,
    CastingFile,
    UnitStatus,
    load_artifact,
    save_artifact,
    text_hash,
)
from ..config import Settings
from ..models import resolve_model
from ..workdir import BookPaths
from .backend import Backend
from .kokoro import KokoroBackend


def make_backend(cfg: Settings) -> Backend:
    if cfg.tts.backend != "kokoro":
        raise ValueError(f"unknown tts backend {cfg.tts.backend!r}")
    model = resolve_model(cfg.models_dir, "kokoro-v1")
    voices = resolve_model(cfg.models_dir, "kokoro-voices-v1")
    if model is None or voices is None:
        raise FileNotFoundError("kokoro model not downloaded — run `castbook models pull` first")
    return KokoroBackend(model, voices)


def run(book: BookPaths, cfg: Settings, log: Callable[[str], None] = print) -> Path:
    attribution = load_artifact(AttributionFile, book.dir)
    casting = load_artifact(CastingFile, book.dir)
    if attribution is None or casting is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook analyze` and `castbook cast` first")

    backend = make_backend(cfg)
    manifest = load_artifact(AudioManifest, book.dir)
    if manifest is None or manifest.input_hash != attribution.input_hash:
        manifest = AudioManifest(book_id=book.book_id, input_hash=attribution.input_hash)

    total = len(attribution.units)
    rendered = skipped = failed = 0
    for i, unit in enumerate(attribution.units):
        voice = casting.map.get(unit.speaker) or casting.map["narrator"]
        unit_hash = text_hash(unit.text + voice.model_dump_json())
        existing = manifest.units.get(unit.id)
        wav = book.unit_wav(unit.id)
        if (
            existing
            and existing.unit_hash == unit_hash
            and existing.status == UnitStatus.done
            and wav.exists()
        ):
            skipped += 1
            continue
        try:
            duration = backend.synthesize(unit.text, voice, wav)
            manifest.units[unit.id] = AudioEntry(
                path=wav.name,
                duration_s=round(duration, 3),
                status=UnitStatus.done,
                unit_hash=unit_hash,
            )
            rendered += 1
        except Exception as e:
            manifest.units[unit.id] = AudioEntry(
                path="", duration_s=0.0, status=UnitStatus.failed, unit_hash=unit_hash
            )
            failed += 1
            log(f"[tts] {unit.id} failed: {e}")
        if (i + 1) % 10 == 0 or i + 1 == total:
            save_artifact(manifest, book.dir)
            log(f"[tts] {i + 1}/{total} units ({rendered} new, {skipped} cached, {failed} failed)")

    save_artifact(manifest, book.dir)
    return book.dir / "manifest.json"
