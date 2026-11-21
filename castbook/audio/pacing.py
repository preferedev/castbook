"""Chapter assembly — concatenate unit wavs with a pause schedule.

Silence rules (seconds): speaker change 0.4, same-speaker paragraph 0.35,
scene break (unit ending in a break marker) 0.8.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..artifacts import Unit
from ..tts.backend import SAMPLE_RATE

PAUSE_SAME = 0.35
PAUSE_SPEAKER = 0.4
PAUSE_SCENE = 0.8
SCENE_BREAK = re.compile(r"(\*\s*){3,}|—\s*—\s*—|⁂")


def silence(seconds: float) -> npt.NDArray[np.float32]:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def pause_after(prev: Unit, nxt: Unit) -> float:
    if SCENE_BREAK.search(prev.text.rstrip()[-12:]):
        return PAUSE_SCENE
    return PAUSE_SPEAKER if prev.speaker != nxt.speaker else PAUSE_SAME


def assemble(units: list[Unit], wav_for: dict[str, Path]) -> npt.NDArray[np.float32]:
    parts: list[npt.NDArray[np.float32]] = []
    prev: Unit | None = None
    for u in units:
        wav = wav_for.get(u.id)
        if wav is None or not wav.exists():
            continue
        if prev is not None:
            parts.append(silence(pause_after(prev, u)))
        data, sr = sf.read(str(wav), dtype="float32")
        if sr != SAMPLE_RATE:
            raise ValueError(f"{wav}: sample rate {sr}, expected {SAMPLE_RATE}")
        parts.append(data)
        prev = u
    if not parts:
        raise ValueError("no rendered units to assemble")
    return np.concatenate(parts)
