"""Synthesize stage — attribution + casting → per-unit wavs + manifest.

Resume rule: a unit re-renders only when its rendered hash (text + resolved
VoiceSpec) differs from the manifest entry, or its wav is missing.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path

from ..artifacts import (
    AttributionFile,
    AudioEntry,
    AudioManifest,
    CastingFile,
    ChaptersFile,
    Unit,
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


def make_backend(cfg: Settings, language: str = "en") -> Backend:
    language = language.split("-")[0].split("_")[0].lower() or "en"
    if cfg.tts.backend == "qwen":
        from .qwen import QwenBackend

        return QwenBackend(language=language)
    if cfg.tts.backend == "pocket":
        from .pocket import PocketBackend

        return PocketBackend(language=language)
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
    if voice.speed <= 0:
        return voice
    out = voice if emotion == "neutral" else voice.model_copy(update={"emotion": emotion})
    factor = EMOTION_SPEED.get(emotion, 1.0) * speed
    if factor == 1.0:
        return out
    # clamp the factor to what keeps voice.speed * factor inside the backend's
    # range — clamping the product directly could invert the intended direction
    lo, hi = 0.5 / voice.speed, 2.0 / voice.speed
    factor = max(lo, min(hi, factor))
    return out.model_copy(update={"speed": voice.speed * factor})


def _load_lexicon(book: BookPaths, cfg: Settings) -> dict[str, str]:
    import json

    out: dict[str, str] = {}
    for f in (cfg.data_dir / "lexicon.json", book.dir / "lexicon.json"):
        if f.exists():
            try:
                out.update({str(k): str(v) for k, v in json.load(f.open()).items()})
            except (json.JSONDecodeError, OSError):
                continue
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
    limit: int | None = None,
    workers: int = 1,
    dry_run: bool = False,
    cancel: threading.Event | None = None,
) -> Path:
    attribution = load_artifact(AttributionFile, book.dir)
    casting = load_artifact(CastingFile, book.dir)
    if attribution is None or casting is None:
        raise FileNotFoundError(f"{book.dir} — run `castbook analyze` and `castbook cast` first")

    if backend is None:
        stale = [k for k, v in casting.map.items() if v.backend != cfg.tts.backend]
        if stale:
            for k in stale:
                del casting.map[k]
            save_artifact(casting, book.dir)
            log(f"[tts] dropped {len(stale)} voice(s) from another backend: {', '.join(stale)}")

    injected_backend = backend is not None
    lexicon = _load_lexicon(book, cfg)
    manifest = load_artifact(AudioManifest, book.dir)
    if manifest is None or manifest.input_hash != attribution.input_hash:
        manifest = AudioManifest(book_id=book.book_id, input_hash=attribution.input_hash)
    units = [u for u in attribution.units if chapters is None or u.chapter in chapters]
    if limit is not None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        units = units[:limit]
    if workers < 1:
        raise ValueError(f"workers must be >= 1, got {workers}")
    if injected_backend:
        workers = 1  # injected backend instances are not thread-shared
    chapters_file = load_artifact(ChaptersFile, book.dir)
    language = chapters_file.meta.language if chapters_file else "en"
    if not dry_run and workers <= 1 and backend is None:
        backend = make_backend(cfg, language)
    total = len(units)
    rendered = skipped = failed = done_i = 0

    def render(unit: Unit, be: Backend) -> tuple[str, float, str, str, str]:
        base = casting.map.get(unit.speaker) or casting.map["narrator"]
        voice = _unit_voice(base, unit.emotion, speed)
        text = _apply_lexicon(unit.text, lexicon)
        unit_hash = text_hash(text + voice.model_dump_json() + language)
        wav = book.unit_wav(unit.id)
        duration = be.synthesize(text, voice, wav)
        return unit.id, duration, wav.name, unit_hash, unit.text[:60]

    pending = []
    for unit in units:
        base = casting.map.get(unit.speaker) or casting.map["narrator"]
        voice = _unit_voice(base, unit.emotion, speed)
        text = _apply_lexicon(unit.text, lexicon)
        unit_hash = text_hash(text + voice.model_dump_json() + language)
        existing = manifest.units.get(unit.id)
        if (
            existing
            and existing.unit_hash == unit_hash
            and existing.status == UnitStatus.done
            and book.unit_wav(unit.id).exists()
        ):
            skipped += 1
        else:
            pending.append(unit)

    if dry_run:
        log(f"[tts] {total} units: {len(pending)} pending, {skipped} cached")
        return book.dir / "manifest.json"
    if pending:
        manifest.started_at = time.time()
        save_artifact(manifest, book.dir)

    if workers > 1 and pending:
        import os
        import threading
        from concurrent.futures import ThreadPoolExecutor

        tls = threading.local()
        import queue

        ready: queue.Queue[Backend] = queue.Queue()
        ready.put(make_backend(cfg, language))  # fail fast + hand off to first worker

        def render_t(unit: Unit) -> tuple[str, float, str, str, str]:
            try:
                be = ready.get_nowait()
            except queue.Empty:
                if not hasattr(tls, "backend"):
                    tls.backend = make_backend(cfg, language)
                be = tls.backend
            return render(unit, be)

        pool = ThreadPoolExecutor(max_workers=min(workers, os.cpu_count() or 1))
        futures = [pool.submit(render_t, u) for u in pending]
        try:
            for f in futures:
                if cancel is not None and cancel.is_set():
                    log(f"[tts] cancelled at {done_i + skipped}/{total}")
                    break
                done_i += 1
                try:
                    uid, dur, name, uh, _ = f.result()
                    manifest.units[uid] = AudioEntry(
                        path=name,
                        duration_s=round(dur, 3),
                        status=UnitStatus.done,
                        unit_hash=uh,
                        done_at=time.time(),
                    )
                    rendered += 1
                except Exception as e:
                    manifest.units[pending[done_i - 1].id] = AudioEntry(
                        path="",
                        duration_s=0.0,
                        status=UnitStatus.failed,
                        unit_hash="",
                    )
                    failed += 1
                    log(f"[tts] {pending[done_i - 1].id} failed: {e}")
                if done_i % 10 == 0 or done_i == len(futures):
                    save_artifact(manifest, book.dir)
                    log(
                        f"[tts] {done_i + skipped}/{total} units "
                        f"({rendered} new, {skipped} cached, {failed} failed)"
                    )
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    else:
        for unit in pending:
            if cancel is not None and cancel.is_set():
                log(f"[tts] cancelled at {done_i + skipped}/{total}")
                break
            done_i += 1
            try:
                uid, dur, name, uh, _ = render(unit, backend)  # type: ignore[arg-type]
                manifest.units[uid] = AudioEntry(
                    path=name,
                    duration_s=round(dur, 3),
                    status=UnitStatus.done,
                    unit_hash=uh,
                    done_at=time.time(),
                )
                rendered += 1
            except Exception as e:
                base = casting.map.get(unit.speaker) or casting.map["narrator"]
                voice = _unit_voice(base, unit.emotion, speed)
                uh = text_hash(_apply_lexicon(unit.text, lexicon) + voice.model_dump_json())
                manifest.units[unit.id] = AudioEntry(
                    path="", duration_s=0.0, status=UnitStatus.failed, unit_hash=uh
                )
                failed += 1
                log(f"[tts] {unit.id} failed: {e}")
            if done_i % 10 == 0 or done_i == len(pending):
                save_artifact(manifest, book.dir)
                log(
                    f"[tts] {done_i + skipped}/{total} units "
                    f"({rendered} new, {skipped} cached, {failed} failed)"
                )

    save_artifact(manifest, book.dir)
    return book.dir / "manifest.json"


# rough render rate measured on CPU: audio-seconds produced per wall-second
_EST_RATE = {"pocket": 6.0, "kokoro": 1.0, "qwen": 0.3}
# typical narration pace in characters per second of audio
_CPS = 15.0


def estimate_render(book: BookPaths, cfg: Settings) -> dict[str, float | int | str]:
    """Pending units + a rough render-time estimate for the configured backend."""
    attribution = load_artifact(AttributionFile, book.dir)
    casting = load_artifact(CastingFile, book.dir)
    if attribution is None or casting is None:
        raise FileNotFoundError(
            f"{book.dir} — run `castbook analyze` and `castbook cast` first"
        )
    lexicon = _load_lexicon(book, cfg)
    manifest = load_artifact(AudioManifest, book.dir)
    if manifest is None or manifest.input_hash != attribution.input_hash:
        manifest = AudioManifest(book_id=book.book_id, input_hash=attribution.input_hash)
    chapters_file = load_artifact(ChaptersFile, book.dir)
    language = chapters_file.meta.language if chapters_file else "en"
    pending: list[Unit] = []
    for unit in attribution.units:
        base = casting.map.get(unit.speaker) or casting.map["narrator"]
        voice = _unit_voice(base, unit.emotion, 1.0)
        text = _apply_lexicon(unit.text, lexicon)
        unit_hash = text_hash(text + voice.model_dump_json() + language)
        existing = manifest.units.get(unit.id)
        if not (
            existing
            and existing.unit_hash == unit_hash
            and existing.status == UnitStatus.done
            and book.unit_wav(unit.id).exists()
        ):
            pending.append(unit)
    chars = sum(len(u.text) for u in pending)
    audio_secs = chars / _CPS
    rate = _EST_RATE.get(cfg.tts.backend, 1.0)
    return {
        "pending": len(pending),
        "total": len(attribution.units),
        "est_audio_min": audio_secs / 60,
        "est_render_min": audio_secs / rate / 60,
        "backend": cfg.tts.backend,
    }
