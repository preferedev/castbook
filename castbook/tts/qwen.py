"""Qwen3-TTS VoiceDesign backend — designed voices from text descriptions (GPU-class).

Each character's `VoiceSpec.voice` holds a natural-language voice description
(built from the character's `vibe` note during casting); the VoiceDesign model
renders a consistent voice for it. Requires the `qwen` extra and a GPU; on CPU
this is technically runnable but far too slow to be practical.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from ..artifacts import VoiceSpec
from .backend import Backend, Capabilities
from .pocket import _atempo, _duration_s, _split

DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
LANGUAGE_NAMES = ["zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"]


class QwenBackend(Backend):
    name = "qwen3-tts-voicedesign"

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        from qwen_tts import Qwen3TTSModel  # type: ignore[import-not-found]

        self._model = Qwen3TTSModel.from_pretrained(model_id)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            mixing=False,
            cloning=True,
            streaming=True,
            languages=LANGUAGE_NAMES,
        )

    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        instruct = voice.voice  # voice slot holds the design description
        samples: list[npt.NDArray[np.float32]] = []
        sr = 0
        for piece in _split(text):
            wavs, sr = self._model.generate_voice_design(
                text=[piece],
                language=["English"],
                instruct=[instruct],
                non_streaming_mode=True,
            )
            samples.append(np.asarray(wavs[0], dtype=np.float32))
        if not samples or not sr:
            raise ValueError("qwen3-tts produced no audio")
        data = np.concatenate(samples)
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
