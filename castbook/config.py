"""Settings — config.toml at the boundary, typed everywhere inside."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, Field

DEFAULT_CONFIG = """\
# Castbook configuration
data_dir = "books"            # per-book workdirs live here
models_dir = "models"         # downloaded model weights

[llm]
# "heuristic" runs with no model (tests/CI/weak CPUs). "llamacpp" uses a local GGUF.
backend = "llamacpp"
model = "qwen3-4b-q4"
gpu_layers = 0                # 0 = CPU; raise when llama.cpp has GPU offload
context = 32768
max_tokens_per_unit = 48
temperature = 0.2

[tts]
backend = "kokoro"
# kokoro-onnx model + voices files are fetched by `castbook models pull`.

[export]
format = "m4b"                # m4b | mp3 | both
"""


class LlmSettings(BaseModel):
    backend: str = "llamacpp"
    model: str = "qwen3-4b-q4"
    gpu_layers: int = 0
    context: int = 32768
    max_tokens_per_unit: int = 48
    temperature: float = 0.2
    base_url: str | None = None  # BYO OpenAI-compatible endpoint (opt-in)


class TtsSettings(BaseModel):
    backend: str = "kokoro"


class ExportSettings(BaseModel):
    format: str = "m4b"


class Settings(BaseModel):
    data_dir: Path = Path("books")
    models_dir: Path = Path("models")
    llm: LlmSettings = Field(default_factory=LlmSettings)
    tts: TtsSettings = Field(default_factory=TtsSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or Path(os.environ.get("CASTBOOK_CONFIG", "config.toml"))
        overrides: dict[str, object] = {}
        if d := os.environ.get("CASTBOOK_DATA_DIR"):
            overrides["data_dir"] = d
        if d := os.environ.get("CASTBOOK_MODELS_DIR"):
            overrides["models_dir"] = d
        if path.exists():
            return cls.model_validate({**tomllib.loads(path.read_text()), **overrides})
        return cls.model_validate(overrides)

    def save_default(self, path: Path) -> Path:
        path.write_text(DEFAULT_CONFIG)
        return path
