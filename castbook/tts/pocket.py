"""Pocket-TTS backend via pocket-tts — MIT code / CC-BY-4.0 voices, CPU-native.

Supports voice cloning: voice spec is a catalog voice name, a local
wav/mp3 clip, or an hf:// path. ~6x realtime on a modern CPU.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..artifacts import VoiceSpec
from .backend import Backend, Capabilities

MAX_CHARS = 2000

_LANG_NAMES = {
    "en": "english",
    "fr": "french",
    "de": "german",
    "pt": "portuguese",
    "it": "italian",
    "es": "spanish",
    "nl": "dutch",
}


class PocketBackend(Backend):
    def __init__(self, language: str = "english") -> None:
        from pocket_tts import TTSModel

        language = language.split("-")[0].split("_")[0].lower()
        self._model = TTSModel.load_model(_LANG_NAMES.get(language, language))
        self._states: dict[str, object] = {}

    def capabilities(self) -> Capabilities:
        return Capabilities(
            cloning=True,
            streaming=True,
            languages=["en", "fr", "de", "pt", "it", "es", "nl"],
        )

    def _voice_state(self, name: str) -> object:
        import re

        if not (re.fullmatch(r"[a-z][a-z0-9_]*", name) or Path(name).is_file()):
            raise ValueError(f"unknown pocket voice {name!r} (catalog name or local audio file)")
        if name not in self._states:
            self._states[name] = self._model.get_state_for_audio_prompt(name)
        return self._states[name]

    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        state = self._voice_state(voice.voice)
        samples: list[npt.NDArray[np.float32]] = []
        for piece in _split(text):
            audio = self._model.generate_audio(state, piece)
            samples.append(np.asarray(audio.numpy(), dtype=np.float32))
        if not samples:
            raise ValueError("pocket-tts produced no audio")
        data = np.concatenate(samples)
        sr = int(self._model.sample_rate)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_wav.with_name(out_wav.stem + ".tmp.wav")
        sf.write(str(tmp), data, sr)
        if voice.speed != 1.0:
            stretched = out_wav.with_name(out_wav.stem + ".stretched.wav")
            _atempo(tmp, voice.speed, stretched)
            stretched.replace(out_wav)
            tmp.unlink(missing_ok=True)
        else:
            tmp.replace(out_wav)
        return _duration_s(out_wav)


def _atempo(src: Path, speed: float, dst: Path) -> None:
    """Pitch-correct tempo change via ffmpeg atempo (0.5-2.0 per filter pass)."""
    import subprocess

    chain: list[str] = []
    rate = speed
    while rate > 2.0:
        chain.append("atempo=2.0")
        rate /= 2.0
    while rate < 0.5:
        chain.append("atempo=0.5")
        rate *= 2.0
    chain.append(f"atempo={rate}")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", ",".join(chain), str(dst)],
        check=True,
    )


def _duration_s(wav: Path) -> float:
    info = sf.info(str(wav))
    return float(info.frames) / float(info.samplerate)


def _split(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    buf = ""
    for s in sentences:
        while len(s) > MAX_CHARS:  # a sentence longer than the cap: split on words
            if buf:
                out.append(buf)
                buf = ""
            cut = s.rfind(" ", 0, MAX_CHARS)
            if cut < MAX_CHARS // 2:
                cut = MAX_CHARS
            out.append(s[:cut])
            s = s[cut:].lstrip()
        if len(buf) + len(s) + 1 > MAX_CHARS and buf:
            out.append(buf)
            buf = ""
        buf = f"{buf} {s}".strip() if buf else s
    if buf:
        out.append(buf)
    return [p for p in out if p.strip()]
