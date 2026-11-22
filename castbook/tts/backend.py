"""TTS backend interface — pluggable engines behind one surface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from ..artifacts import VoiceSpec

SAMPLE_RATE = 24000


class Capabilities(BaseModel):
    cloning: bool = False
    emotion_tags: bool = False
    streaming: bool = False
    languages: list[str] = ["en"]
    vram_gb: float = 0.0


class Backend(ABC):
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abstractmethod
    def synthesize(self, text: str, voice: VoiceSpec, out_wav: Path) -> float:
        """Render `text` with `voice` to `out_wav`; return duration in seconds."""
        ...
