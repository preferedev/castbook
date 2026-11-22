

def test_normalize_speaker() -> None:
    from castbook.analyze.llm import _normalize_speaker
    from castbook.artifacts import Character

    cast = [
        Character(id="a", name="Elizabeth Bennet", aliases=["Lizzy", "Eliza"]),
        Character(id="b", name="March Hare", aliases=[]),
    ]
    assert _normalize_speaker("lizzy", cast) == "elizabeth bennet"
    assert _normalize_speaker("miss elizabeth bennet", cast) == "elizabeth bennet"
    assert _normalize_speaker("the march hare", cast) == "march hare"
    assert _normalize_speaker("narrator", cast) == "narrator"
    assert _normalize_speaker("unknown stranger", cast) == "unknown stranger"
