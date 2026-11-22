

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


def test_normalize_speaker_shared_surname() -> None:
    from castbook.analyze.llm import _normalize_speaker
    from castbook.artifacts import Character

    cast = [
        Character(id="a", name="Mr Bennet", aliases=[]),
        Character(id="b", name="Mrs Bennet", aliases=[]),
    ]
    # exact match misses on the period; surname match must not grab Mr. Bennet
    assert _normalize_speaker("mrs. bennet", cast) == "mrs bennet"
    assert _normalize_speaker("mr. bennet", cast) == "mr bennet"
    cast2 = [
        Character(id="a", name="Mr. Bennet", aliases=[]),
        Character(id="b", name="Lady Catherine", aliases=["Lady Catherine de Bourgh"]),
    ]
    assert _normalize_speaker("elder mr. bennet", cast2) == "mr. bennet"
