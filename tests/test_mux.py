"""Export verification: muxed M4B carries chapter marks ffprobe can read."""

import json
import subprocess

import numpy as np
import soundfile as sf

from castbook.artifacts import BookMeta
from castbook.audio.mux import mux_m4b
from castbook.tts.backend import SAMPLE_RATE


def _wav(path, seconds: float) -> None:
    sf.write(path, np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32), SAMPLE_RATE)


def test_m4b_has_chapters_and_metadata(tmp_path) -> None:
    workdir = tmp_path / "work"
    workdir.mkdir()
    w1, w2 = tmp_path / "0.wav", tmp_path / "1.wav"
    _wav(w1, 0.5)
    _wav(w2, 0.5)
    out = tmp_path / "book.m4b"
    mux_m4b([w1, w2], ["One", "Two"], BookMeta(title="T", author="A"), out, workdir)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_chapters", "-show_format", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)
    chapters = info["chapters"]
    assert len(chapters) == 2
    titles = [c["tags"]["title"] for c in chapters]
    assert titles == ["One", "Two"]
    assert float(info["format"]["duration"]) >= 0.9
    assert info["format"]["tags"]["title"] == "T"
