"""Machine capability probe — picks a sane TTS/LLM tier per machine.

Reports a tier the UI and doctor can print: "GPU found — expect
~15x realtime" vs "CPU only — expect ~2x".
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class MachineInfo:
    tier: str  # "cuda" | "mps" | "cpu"
    gpu: str | None
    cores: int
    ram_gb: float
    detail: str

    @property
    def quality_capable(self) -> bool:
        return self.tier != "cpu"

    @property
    def verdict(self) -> str:
        if self.tier == "cuda":
            return (
                f"GPU found ({self.gpu}) — quality tier (Qwen3-TTS) available, expect ~15x realtime"
            )
        if self.tier == "mps":
            return "Apple Silicon GPU found — quality tier available, expect ~10x realtime"
        return "CPU only — expect ~0.5-2x realtime; Kokoro + Qwen3-4B-LLM recommended"


def detect() -> MachineInfo:
    cores = os.cpu_count() or 1
    ram = _ram_gb()
    gpu = _nvidia_gpu()
    if gpu:
        return MachineInfo("cuda", gpu, cores, ram, "nvidia-smi")
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        import importlib.util

        if importlib.util.find_spec("torch") is not None:
            import importlib

            torch = importlib.import_module("torch")
            if torch.backends.mps.is_available():
                return MachineInfo("mps", "apple-silicon", cores, ram, "torch.backends.mps")
    return MachineInfo("cpu", None, cores, ram, "no discrete GPU found")


def _nvidia_gpu() -> str | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        name = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        return name or None
    except (subprocess.SubprocessError, OSError):
        return None


def _ram_gb() -> float:
    try:
        from pathlib import Path

        with Path("/proc/meminfo").open() as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024**2, 1)
    except OSError:
        pass
    return 0.0
