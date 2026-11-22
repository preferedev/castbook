"""Voice library — versioned, license-clean entries for the default backend.

Source: Kokoro-82M preset voices (Apache-2.0) via kokoro-onnx.
`age`/`pitch`/`energy` are rough tags used only by the matcher.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class VoiceEntry(BaseModel):
    id: str
    backend: str = "kokoro"
    gender: str  # f | m
    age: str  # young | adult | old
    pitch: str = "mid"  # low | mid | high
    energy: str = "mid"  # low | mid | high
    description: str = ""


LIBRARY: list[VoiceEntry] = [
    VoiceEntry(id="af_heart", gender="f", age="adult", description="warm, steady alto"),
    VoiceEntry(id="af_bella", gender="f", age="young", energy="high", description="bright, lively"),
    VoiceEntry(id="af_nicole", gender="f", age="adult", pitch="low", description="soft, intimate"),
    VoiceEntry(id="af_sarah", gender="f", age="adult", energy="low", description="calm narrator"),
    VoiceEntry(id="af_sky", gender="f", age="young", pitch="high", description="airy, light"),
    VoiceEntry(id="af_river", gender="f", age="adult", energy="low", description="measured, cool"),
    VoiceEntry(id="bf_emma", gender="f", age="adult", description="british, crisp"),
    VoiceEntry(
        id="bf_isabella",
        gender="f",
        age="adult",
        pitch="low",
        description="british, rich",
    ),
    VoiceEntry(id="bf_alice", gender="f", age="young", description="british, clear"),
    VoiceEntry(id="bf_lily", gender="f", age="old", pitch="high", description="british, older"),
    VoiceEntry(id="am_adam", gender="m", age="adult", description="deep, steady"),
    VoiceEntry(id="am_michael", gender="m", age="adult", energy="high", description="assertive"),
    VoiceEntry(id="am_echo", gender="m", age="young", pitch="mid", description="light tenor"),
    VoiceEntry(id="am_eric", gender="m", age="adult", pitch="low", description="gravel-adjacent"),
    VoiceEntry(id="am_fenrir", gender="m", age="young", energy="high", description="energetic"),
    VoiceEntry(id="am_liam", gender="m", age="young", description="earnest"),
    VoiceEntry(
        id="am_onyx",
        gender="m",
        age="adult",
        pitch="low",
        energy="low",
        description="dark bass",
    ),
    VoiceEntry(id="am_puck", gender="m", age="young", pitch="high", description="playful"),
    VoiceEntry(id="am_santa", gender="m", age="old", pitch="low", description="booming, warm"),
    VoiceEntry(
        id="bm_george",
        gender="m",
        age="old",
        pitch="low",
        description="british, dignified",
    ),
    VoiceEntry(id="bm_lewis", gender="m", age="adult", description="british, dry"),
    VoiceEntry(
        id="bm_fable",
        gender="m",
        age="adult",
        energy="high",
        description="british, animated",
    ),
    VoiceEntry(id="bm_daniel", gender="m", age="adult", energy="low", description="british, flat"),
]

DEFAULT_NARRATOR = "af_sarah"
DEFAULT_AMBIGUOUS = "bm_daniel"


def get(voice_id: str) -> VoiceEntry | None:
    return next((v for v in LIBRARY if v.id == voice_id), None)


def pool(gender: str, age: str = "") -> list[VoiceEntry]:
    g = "f" if gender == "f" else "m" if gender == "m" else ""
    voices = [v for v in LIBRARY if (v.gender == g if g else True)]
    if age == "old":
        aged = [v for v in voices if v.age == "old"]
        if aged:
            return aged
    return voices


def _norm(name: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def load_memory(data_dir: Path) -> dict[str, str]:
    import json

    f = Path(data_dir) / "voice-memory.json"
    if not f.exists():
        return {}
    return {str(k): str(v) for k, v in json.load(f.open()).items()}


def save_memory(data_dir: Path, mapping: dict[str, str]) -> None:
    import json

    merged = {**load_memory(data_dir), **{_norm(k): v for k, v in mapping.items()}}
    Path(data_dir, "voice-memory.json").write_text(json.dumps(merged, indent=2))
