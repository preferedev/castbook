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
