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
    VoiceSpec,
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


EMOTION_SPEED = {
    "joyful": 1.05,
    "angry": 1.10,
    "shouted": 1.15,
    "sarcastic": 1.02,
    "fearful": 0.95,
    "sad": 0.90,
    "whispered": 0.85,
}


def _unit_voice(voice: VoiceSpec, emotion: str, speed: float = 1.0) -> VoiceSpec:
    factor = EMOTION_SPEED.get(emotion, 1.0) * speed
    if factor == 1.0:
        return voice
    return voice.model_copy(update={"speed": max(0.7, min(1.4, voice.speed * factor))})


def _load_lexicon(book: BookPaths, cfg: Settings) -> dict[str, str]:
    import json

    out: dict[str, str] = {}
    for f in (cfg.data_dir / "lexicon.json", book.dir / "lexicon.json"):
        if f.exists():
            out.update({str(k): str(v) for k, v in json.load(f.open()).items()})
    return out


def _apply_lexicon(text: str, lex: dict[str, str]) -> str:
    import re

    for word, repl in lex.items():
        text = re.sub(rf"\b{re.escape(word)}\b", repl, text)
    return text


def run(
    book: BookPaths,
    cfg: Settings,
    log: Callable[[str], None] = print,
    backend: Backend | None = None,
    chapters: set[int] | None = None,
    speed: float = 1.0,
) -> Path:
    attribution = load_artifact(AttributionFile, book.dir)
    casting = load_artifact(CastingFile, book.dir)
    if attribution is None or casting is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook analyze` and `castbook cast` first")

    backend = backend or make_backend(cfg)
    lexicon = _load_lexicon(book, cfg)
    manifest = load_artifact(AudioManifest, book.dir)
    if manifest is None or manifest.input_hash != attribution.input_hash:
        manifest = AudioManifest(book_id=book.book_id, input_hash=attribution.input_hash)

    units = [u for u in attribution.units if chapters is None or u.chapter in chapters]
    total = len(units)
    rendered = skipped = failed = 0
    for i, unit in enumerate(units):
        base = casting.map.get(unit.speaker) or casting.map["narrator"]
        voice = _unit_voice(base, unit.emotion, speed)
        text = _apply_lexicon(unit.text, lexicon)
        unit_hash = text_hash(text + voice.model_dump_json())
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
            duration = backend.synthesize(text, voice, wav)
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
