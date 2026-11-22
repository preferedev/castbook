"""Versioned JSON artifacts — the only interface between pipeline stages.

Every stage reads its inputs from and writes its outputs to these files under
books/<id>/. Stages never import each other's internals.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field

SCHEMA: Literal[1] = 1

RESERVED_NARRATOR = "narrator"
RESERVED_AMBIGUOUS = "ambiguous"
RESERVED_SPEAKERS = frozenset({RESERVED_NARRATOR, RESERVED_AMBIGUOUS})

Emotion = Literal[
    "neutral",
    "angry",
    "sad",
    "joyful",
    "fearful",
    "whispered",
    "shouted",
    "sarcastic",
]
EMOTIONS: tuple[str, ...] = (
    "neutral",
    "angry",
    "sad",
    "joyful",
    "fearful",
    "whispered",
    "shouted",
    "sarcastic",
)

Role = Literal["protagonist", "major", "minor", "one_off"]
Gender = Literal["m", "f", "nb", "unknown"]
UnitKind = Literal["dialogue", "narration", "mixed"]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class BookMeta(BaseModel):
    title: str = "Untitled"
    author: str = "Unknown"
    language: str = "en"
    source_file: str = ""
    cover_path: str | None = None


class Chapter(BaseModel):
    index: int
    title: str
    text: str
    word_count: int
    source: dict[str, Any] = Field(default_factory=dict)


class ChaptersFile(BaseModel):
    schema_: Literal[1] = Field(default=SCHEMA, alias="schema")
    book_id: str
    meta: BookMeta
    chapters: list[Chapter]
    input_hash: str


class Character(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    gender: Gender = "unknown"
    age: str = "unknown"
    role: Role = "minor"
    vibe: str = ""


class CastFile(BaseModel):
    schema_: Literal[1] = Field(default=SCHEMA, alias="schema")
    book_id: str
    characters: list[Character]
    input_hash: str


class Unit(BaseModel):
    id: str
    chapter: int
    text: str
    speaker: str  # character id, RESERVED_NARRATOR, or RESERVED_AMBIGUOUS
    emotion: Emotion = "neutral"
    kind: UnitKind = "narration"


class AttributionFile(BaseModel):
    schema_: Literal[1] = Field(default=SCHEMA, alias="schema")
    book_id: str
    attributor: str
    units: list[Unit]
    needs_review: list[str] = Field(default_factory=list)
    input_hash: str


class VoiceSpec(BaseModel):
    backend: str
    voice: str
    seed: int = 0
    speed: float = 1.0
    emotion: str = "neutral"  # backends with style control (qwen) may read this


class CastingFile(BaseModel):
    schema_: Literal[1] = Field(default=SCHEMA, alias="schema")
    book_id: str
    map: dict[str, VoiceSpec]
    input_hash: str


class UnitStatus(str, Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class ChapterStatus(str, Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class AudioEntry(BaseModel):
    path: str
    duration_s: float
    status: UnitStatus
    unit_hash: str
    done_at: float = 0.0


class ChapterAudio(BaseModel):
    path: str
    duration_s: float
    status: ChapterStatus


class AudioManifest(BaseModel):
    schema_: Literal[1] = Field(default=SCHEMA, alias="schema")
    book_id: str
    units: dict[str, AudioEntry] = Field(default_factory=dict)
    chapters: dict[str, ChapterAudio] = Field(default_factory=dict)
    input_hash: str = ""
    started_at: float = 0.0


class ModelSpec(BaseModel):
    """One downloadable model in models/manifest."""

    id: str
    kind: Literal["llm", "tts"]
    url: str
    filename: str
    size_bytes: int
    sha256: str
    license: str
    required: bool = False


def _file_stem(cls: type[BaseModel]) -> str:
    return {
        ChaptersFile: "chapters",
        CastFile: "cast",
        AttributionFile: "attribution",
        CastingFile: "casting",
        AudioManifest: "manifest",
    }[cls]


def save_artifact(model: BaseModel, directory: Path) -> Path:
    """Atomically write an artifact — never overwrite a good file with a partial."""
    path = directory / f"{_file_stem(type(model))}.json"
    fd, tmp_name = tempfile.mkstemp(dir=directory, suffix=".tmp", prefix=".write-")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(model.model_dump_json(by_alias=True, indent=2))
        Path(tmp_name).replace(path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path


T = TypeVar("T", bound=BaseModel)


def load_artifact(cls: type[T], directory: Path) -> T | None:
    path = directory / f"{_file_stem(cls)}.json"
    if not path.exists():
        return None
    return cls.model_validate(json.loads(path.read_text()))
