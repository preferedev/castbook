from castbook.artifacts import Character


def test_reconcile_keeps_titled_variants() -> None:
    from castbook.analyze.reconcile import reconcile_cast, speaker_id

    cast = reconcile_cast(
        [
            Character(id="mr-bennet", name="Mr. Bennet"),
            Character(id="mrs-bennet", name="Mrs. Bennet"),
            Character(id="elizabeth", name="Elizabeth Bennet", aliases=["Lizzy"]),
        ]
    )
    assert {c.id for c in cast} == {"mr-bennet", "mrs-bennet", "elizabeth"}
    assert speaker_id("Mrs. Bennet", cast) == "mrs-bennet"
    assert speaker_id("Elizabeth", cast) == "elizabeth"
    assert speaker_id("Bennet", cast) is None


def test_reconcile_merges_bare_into_single_titled() -> None:
    from castbook.analyze.reconcile import reconcile_cast

    cast = reconcile_cast(
        [Character(id="mr-bennet", name="Mr. Bennet"), Character(id="b", name="Bennet")]
    )
    assert [c.id for c in cast] == ["mr-bennet"]
    assert "Bennet" in cast[0].aliases
