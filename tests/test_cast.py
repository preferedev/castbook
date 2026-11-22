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


def test_qwen_cast_uses_vibe_descriptions() -> None:
    from castbook.cast.match import _valid_voice

    chars = [
        Character(
            id="alice", name="Alice", gender="f", role="protagonist", vibe="bright curious girl"
        ),
        Character(id="hatter", name="Hatter", gender="m", role="major", vibe="nervous quick tenor"),
    ]
    m = auto_cast(chars, "book1", backend="qwen")
    assert m["alice"].backend == "qwen"
    assert m["alice"].voice == "bright curious girl"
    assert "narrator" in m["narrator"].voice
    for v in m.values():
        assert _valid_voice(v.voice, set(), "qwen")


def test_preset_detection_by_handle_not_punctuation() -> None:
    from castbook.cast.match import _looks_like_preset

    assert not _looks_like_preset("warm/raspy contralto")
    assert _looks_like_preset("paul")
    assert _looks_like_preset("af_heart")
    assert _looks_like_preset("a+b")


def test_voicepack_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from castbook.artifacts import CastFile, CastingFile, VoiceSpec, save_artifact
    from castbook.cast.voicepack import apply_pack, export_pack
    from castbook.workdir import BookPaths

    b1 = BookPaths(tmp_path / "books", "b1")
    b1.dir.mkdir(parents=True)
    chars = _chars()
    save_artifact(CastFile(book_id="b1", characters=chars, input_hash="h"), b1.dir)
    m = auto_cast(chars, "b1")
    m["elizabeth"] = VoiceSpec(backend="kokoro", voice="af_bella", speed=1.2)
    save_artifact(CastingFile(book_id="b1", map=m, input_hash="h"), b1.dir)

    pack = export_pack(b1)
    assert pack["speakers"]["elizabeth"]["voice"] == "af_bella"
    assert pack["aliases"]["lizzy"] == "elizabeth"

    # second book: same character under a different id via alias match
    b2 = BookPaths(tmp_path / "books", "b2")
    b2.dir.mkdir(parents=True)
    chars2 = [Character(id="lizzy", name="Lizzy", aliases=["Elizabeth"], gender="f", role="major")]
    save_artifact(CastFile(book_id="b2", characters=chars2, input_hash="h"), b2.dir)
    m2 = auto_cast(chars2, "b2")
    save_artifact(CastingFile(book_id="b2", map=m2, input_hash="h"), b2.dir)

    res = apply_pack(b2, pack, "kokoro")
    assert "lizzy" in res["applied"]
    assert "darcy" in res["skipped"]
    from castbook.artifacts import load_artifact

    assert load_artifact(CastingFile, b2.dir).map["lizzy"].voice == "af_bella"
