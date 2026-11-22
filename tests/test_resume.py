"""Resume semantics: re-running generate renders only un-finished units."""

from pathlib import Path

import numpy as np
import soundfile as sf

from castbook.artifacts import (
    AttributionFile,
    AudioManifest,
    CastingFile,
    Unit,
    UnitStatus,
    VoiceSpec,
    load_artifact,
    save_artifact,
)
from castbook.config import Settings
from castbook.tts import run
from castbook.tts.backend import SAMPLE_RATE, Backend, Capabilities
from castbook.workdir import BookPaths


class FakeBackend(Backend):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def capabilities(self) -> Capabilities:
        return Capabilities()

    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        self.calls.append(text)
        sf.write(out_wav, np.ones(SAMPLE_RATE // 10, dtype=np.float32), SAMPLE_RATE)
        return 0.1


def _book(tmp_path: Path, n_units: int = 3) -> BookPaths:
    book = BookPaths(tmp_path, "b1")
    book.ensure()
    units = [
        Unit(id=f"u{i}", chapter=0, kind="dialogue", text=f"line {i}", speaker="hero")
        for i in range(n_units)
    ]
    save_artifact(
        AttributionFile(book_id="b1", attributor="heuristic", units=units, input_hash="h"), book.dir
    )
    casting = CastingFile(
        book_id="b1",
        map={
            "hero": VoiceSpec(backend="fake", voice="v1"),
            "narrator": VoiceSpec(backend="fake", voice="v2"),
            "ambiguous": VoiceSpec(backend="fake", voice="v3"),
        },
        input_hash="h",
    )
    save_artifact(casting, book.dir)
    return book


def test_second_run_synthesizes_nothing(tmp_path) -> None:
    book = _book(tmp_path)
    backend = FakeBackend()
    run(book, Settings(), backend=backend, log=lambda _: None)
    assert len(backend.calls) == 3
    backend.calls.clear()
    run(book, Settings(), backend=backend, log=lambda _: None)
    assert backend.calls == []


def test_voice_change_rerenders_unit(tmp_path) -> None:
    book = _book(tmp_path)
    backend = FakeBackend()
    run(book, Settings(), backend=backend, log=lambda _: None)
    casting = load_artifact(CastingFile, book.dir)
    assert casting is not None
    casting.map["hero"].voice = "v9"
    save_artifact(casting, book.dir)
    backend.calls.clear()
    run(book, Settings(), backend=backend, log=lambda _: None)
    assert len(backend.calls) == 3  # every unit belongs to hero


def test_failed_unit_retried(tmp_path) -> None:
    book = _book(tmp_path, n_units=2)
    backend = FakeBackend()
    run(book, Settings(), backend=backend, log=lambda _: None)
    book.unit_wav("u1").unlink()
    m = load_artifact(AudioManifest, book.dir)
    assert m is not None
    m.units["u1"].status = UnitStatus.failed
    save_artifact(m, book.dir)
    backend.calls.clear()
    run(book, Settings(), backend=backend, log=lambda _: None)
    assert backend.calls == ["line 1"]


def test_emotion_changes_effective_voice() -> None:
    from castbook.artifacts import VoiceSpec
    from castbook.tts import _unit_voice

    v = VoiceSpec(backend="k", voice="v", speed=1.0)
    assert _unit_voice(v, "neutral").speed == 1.0
    assert _unit_voice(v, "shouted").speed == 1.15
    assert _unit_voice(v, "sad").speed == 0.9
    out = _unit_voice(v, "whispered")
    assert out.speed == 0.85 and out.voice == "v"


def test_emotion_pacing_never_inverts_direction() -> None:
    from castbook.artifacts import VoiceSpec
    from castbook.tts import _unit_voice

    slow = VoiceSpec(backend="k", voice="v", speed=0.5)
    fast = VoiceSpec(backend="k", voice="v", speed=1.9)
    assert _unit_voice(slow, "sad").speed <= slow.speed
    assert _unit_voice(slow, "whispered").speed <= slow.speed
    assert (
        _unit_voice(fast, "shouted").speed >= fast.speed - 1e-9
        or _unit_voice(fast, "shouted").speed == 2.0
    )
    zero = VoiceSpec(backend="k", voice="v", speed=0.0)
    assert _unit_voice(zero, "sad") is zero


def test_voice_mix_vector() -> None:
    import numpy as np

    from castbook.tts.kokoro import KokoroBackend

    backend = KokoroBackend.__new__(KokoroBackend)
    a = np.ones((4,), dtype=np.float32)
    b = np.zeros((4,), dtype=np.float32)
    backend._kokoro = type("K", (), {"get_voice_style": lambda self, n: a if n == "va" else b})()
    vec = backend._voice_vector("va:0.75+vb:0.25")
    assert np.allclose(vec, [0.75, 0.75, 0.75, 0.75])
    assert backend._voice_vector("solo") == "solo"
