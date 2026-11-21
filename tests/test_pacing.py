import numpy as np
import soundfile as sf

from castbook.artifacts import Unit
from castbook.audio import pacing


def _u(speaker: str, text: str = "hi") -> Unit:
    return Unit(id=f"u-{text}-{speaker}", chapter=0, kind="dialogue", text=text, speaker=speaker)


def test_pause_rules() -> None:
    a, b = _u("alice"), _u("bob")
    assert pacing.pause_after(a, b) == pacing.PAUSE_SPEAKER
    assert pacing.pause_after(a, _u("alice", "2")) == pacing.PAUSE_SAME
    scene = _u("alice", "end * * *")
    assert pacing.pause_after(scene, b) == pacing.PAUSE_SCENE


def test_assemble_concatenates_with_silence(tmp_path) -> None:
    wav = tmp_path / "u.wav"
    sf.write(wav, np.ones(2400, dtype=np.float32), pacing.SAMPLE_RATE)
    u1, u2 = _u("a", "w1"), _u("b", "w2")
    out = pacing.assemble([u1, u2], {u1.id: wav, u2.id: wav})
    expected = 4800 + int(pacing.PAUSE_SPEAKER * pacing.SAMPLE_RATE)
    assert out.shape[0] == expected
