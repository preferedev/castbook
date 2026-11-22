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


def test_voice_memory_reused_across_books(tmp_path) -> None:
    from castbook.cast.library import load_memory, save_memory
    from castbook.cast.match import auto_cast

    chars = [Character(id="mara", name="Mara", gender="f", role="protagonist")]
    first = auto_cast(chars, "book-a")
    save_memory(tmp_path, {"Mara": first["mara"].voice})
    second = auto_cast(chars, "book-b", memory=load_memory(tmp_path))
    assert second["mara"].voice == first["mara"].voice


def test_merge_pops_only_moved_units(tmp_path) -> None:
    from castbook.analyze.reconcile import merge_speakers
    from castbook.artifacts import (
        AttributionFile,
        AudioEntry,
        AudioManifest,
        CastFile,
        Character,
        Unit,
        UnitStatus,
        load_artifact,
        save_artifact,
    )
    from castbook.workdir import BookPaths

    book = BookPaths(tmp_path, "b1").ensure()
    units = [
        Unit(id="a1", chapter=0, kind="dialogue", text="hi", speaker="hero"),
        Unit(id="a2", chapter=0, kind="dialogue", text="there", speaker="narrator"),
    ]
    save_artifact(
        AttributionFile(book_id="b1", attributor="heuristic", units=units, input_hash="h"), book.dir
    )
    save_artifact(
        CastFile(
            book_id="b1",
            characters=[
                Character(id="hero", name="Hero"),
                Character(id="narrator", name="Narrator"),
            ],
            input_hash="h",
        ),
        book.dir,
    )
    save_artifact(
        AudioManifest(
            book_id="b1",
            units={
                "a1": AudioEntry(
                    status=UnitStatus.done, path="u1.wav", duration_s=1.0, unit_hash="h1"
                ),
                "a2": AudioEntry(
                    status=UnitStatus.done, path="u2.wav", duration_s=1.0, unit_hash="h2"
                ),
            },
            input_hash="h",
        ),
        book.dir,
    )
    assert merge_speakers(book.dir, "hero", "narrator") == 1
    m = load_artifact(AudioManifest, book.dir)
    assert m is not None
    assert set(m.units) == {"a2"}  # narrator's own audio survives; only hero's is re-rendered
