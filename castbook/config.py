"""Settings — config.toml at the boundary, typed everywhere inside."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from pydantic import BaseModel, Field, PrivateAttr

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


QUALITY_PRESETS = {
    # name -> (llm backend, tts backend); explicit flags still override
    "fast": ("heuristic", "pocket"),
    "balanced": ("hybrid", "kokoro"),
    "studio": ("llamacpp", "qwen"),
}


class LlmSettings(BaseModel):
    backend: str = "llamacpp"
    model: str = "qwen3-4b-q4"
    gpu_layers: int = 0
    context: int = 32768
    max_tokens_per_unit: int = 48
    temperature: float = 0.2
    base_url: str | None = None  # BYO OpenAI-compatible endpoint (opt-in)


class TtsSettings(BaseModel):
    backend: str = "kokoro"  # kokoro | pocket | qwen
    # scales the emotion→speed deltas (0 = ignore emotion, 1 = full effect)
    emotion_strength: float = 1.0
    pause_scale: float = 1.0


class ExportSettings(BaseModel):
    format: str = "m4b"


class Settings(BaseModel):
    data_dir: Path = Path("books")
    models_dir: Path = Path("models")
    llm: LlmSettings = Field(default_factory=LlmSettings)
    tts: TtsSettings = Field(default_factory=TtsSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)
    _config_path: Path | None = PrivateAttr(default=None)

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or Path(os.environ.get("CASTBOOK_CONFIG", "config.toml"))
        overrides: dict[str, object] = {}
        if d := os.environ.get("CASTBOOK_DATA_DIR"):
            overrides["data_dir"] = d
        if d := os.environ.get("CASTBOOK_MODELS_DIR"):
            overrides["models_dir"] = d
        if path.exists():
            cfg = cls.model_validate({**tomllib.loads(path.read_text()), **overrides})
        else:
            cfg = cls.model_validate(overrides)
        cfg.tts.emotion_strength = min(2.0, max(0.0, cfg.tts.emotion_strength))
        cfg.tts.pause_scale = min(3.0, max(0.0, cfg.tts.pause_scale))
        cfg._config_path = path
        return cfg

    def save_default(self, path: Path) -> Path:
        path.write_text(DEFAULT_CONFIG)
        return path

    def save(self, path: Path | None = None) -> Path:
        path = path or self._config_path or Path(os.environ.get("CASTBOOK_CONFIG", "config.toml"))
        lines = [
            f"data_dir = {_toml_val(str(self.data_dir))}",
            f"models_dir = {_toml_val(str(self.models_dir))}",
        ]
        for section in ("llm", "tts", "export"):
            lines.append(f"\n[{section}]")
            for k, v in getattr(self, section).model_dump().items():
                if v is None:
                    continue
                lines.append(f"{k} = {_toml_val(v)}")
        path.write_text("\n".join(lines) + "\n")
        return path


def _toml_val(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    esc = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'
