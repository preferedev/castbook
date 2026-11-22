from castbook.artifacts import Character
from castbook.cast.match import auto_cast


def _chars() -> list[Character]:
    return [
        Character(
            id="elizabeth", name="Elizabeth", aliases=["Lizzy"], gender="f", role="protagonist"
        ),
        Character(id="darcy", name="Mr Darcy", gender="m", role="major"),
        Character(id="jane", name="Jane", gender="f", role="major"),
    ]


def test_distinct_voices_for_distinct_characters() -> None:
    m = auto_cast(_chars(), "book1")
    voices = {m[c.id].voice for c in _chars()}
    assert len(voices) == 3
    assert m["narrator"].voice == "af_sarah"
    assert "ambiguous" in m


def test_deterministic() -> None:
    assert auto_cast(_chars(), "b") == auto_cast(_chars(), "b")


def test_book_id_changes_seed() -> None:
    a = auto_cast(_chars(), "a")
    b = auto_cast(_chars(), "b")
    assert any(a[c.id].seed != b[c.id].seed for c in _chars())


def test_cast_pocket_backend(tmp_path) -> None:
    m = auto_cast(_chars(), "book1", backend="pocket")
    assert all(v.backend == "pocket" for v in m.values())
    assert m["narrator"].voice == "paul"
    assert m["ambiguous"].voice == "george"


def test_pocket_memory_uses_pocket_backend() -> None:
    chars = [Character(id="mara", name="Mara", gender="f", role="protagonist")]
    m = auto_cast(chars, "b", memory={"mara": "alba"}, backend="pocket")
    assert m["mara"].backend == "pocket"
    assert m["mara"].voice == "alba"


def test_valid_voice_accepts_existing_clip(tmp_path) -> None:
    from castbook.cast.match import _valid_voice

    clip = tmp_path / "me.wav"
    clip.write_bytes(b"RIFF")
    assert _valid_voice(str(clip), set(), "pocket")
    assert not _valid_voice(str(clip), set(), "kokoro")
    assert not _valid_voice(str(tmp_path / "missing.wav"), set(), "pocket")


def test_mixes_rejected_for_pocket() -> None:
    from castbook.cast.match import _valid_voice

    pocket = {"paul", "george"}
    assert _valid_voice("af_sky:0.6+bf_emma:0.4", {"af_sky", "bf_emma"}, "kokoro")
    assert not _valid_voice("paul:0.6+george:0.4", pocket, "pocket")


def test_pocket_split_bounds() -> None:
    from castbook.tts.pocket import MAX_CHARS, _split

    parts = _split("a " * 3000)
    assert len(parts) > 1
    assert all(len(p) <= MAX_CHARS for p in parts)
    assert "".join(parts)
