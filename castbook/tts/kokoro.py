"""Kokoro-82M backend via kokoro-onnx — Apache-2.0, CPU-friendly, 54 voices."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..artifacts import VoiceSpec
from .backend import SAMPLE_RATE, Backend, Capabilities

MAX_CHARS = 900


class KokoroBackend(Backend):
    def __init__(self, model_path: Path, voices_path: Path) -> None:
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(str(model_path), str(voices_path))

    def capabilities(self) -> Capabilities:
        return Capabilities(streaming=True, languages=["en"])

    def _voice_vector(self, name: str) -> str | npt.NDArray[np.float32]:
        if "+" not in name:
            return name
        parts: list[npt.NDArray[np.float32]] = []
        total = 0.0
        for spec in name.split("+"):
            vname, _, w = spec.partition(":")
            weight = float(w) if w else 1.0
            parts.append(weight * np.asarray(self._kokoro.get_voice_style(vname)))
            total += weight
        if total <= 0:
            raise ValueError(f"bad voice mix {name!r}")
        return sum(parts) / total  # type: ignore[return-value]

    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        samples: list[npt.NDArray[np.float32]] = []
        vec = self._voice_vector(voice.voice)
        for piece in _split(text):
            audio, _ = self._kokoro.create(piece, voice=vec, speed=voice.speed)
            samples.append(np.asarray(audio, dtype=np.float32))
        if not samples:
            raise ValueError("kokoro produced no audio")
        data = np.concatenate(samples)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_wav.with_name(out_wav.stem + ".tmp.wav")
        sf.write(str(tmp), data, SAMPLE_RATE)
        tmp.replace(out_wav)
        return len(data) / SAMPLE_RATE


def _split(text: str) -> list[str]:
    """Kokoro degrades past ~1k chars; split on sentence boundaries."""
    if len(text) <= MAX_CHARS:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        if len(buf) + len(s) + 1 > MAX_CHARS and buf:
            out.append(buf)
            buf = ""
        buf = f"{buf} {s}".strip() if buf else s
    if buf:
        out.append(buf)
    return [p for p in out if p.strip()]
