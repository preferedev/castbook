"""Loudness normalization — ffmpeg loudnorm to audiobook practice."""

from __future__ import annotations

import subprocess
from pathlib import Path

TARGET_LUFS = -19.0
PEAK_DBTP = -1.0


def loudnorm(src: Path, dst: Path, lufs: float = TARGET_LUFS) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".norm.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(src),
        "-af",
        f"loudnorm=I={lufs}:TP={PEAK_DBTP}:LRA=11",
        "-ar",
        "24000",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg loudnorm failed: {r.stderr.strip()[:400]}")
    tmp.replace(dst)
    return dst
