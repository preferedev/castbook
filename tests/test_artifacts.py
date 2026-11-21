from castbook.artifacts import (
    AttributionFile,
    Chapter,
    Unit,
    load_artifact,
    save_artifact,
)


def test_roundtrip(tmp_path) -> None:
    a = AttributionFile(
        book_id="b",
        attributor="heuristic",
        units=[Unit(id="u1", chapter=0, text="t", speaker="narrator")],
        input_hash="h",
    )
    save_artifact(a, tmp_path)
    back = load_artifact(AttributionFile, tmp_path)
    assert back == a


def test_load_missing_returns_none(tmp_path) -> None:
    assert load_artifact(AttributionFile, tmp_path) is None


def test_chapter_serialization() -> None:
    c = Chapter(index=2, title="T", text="body", word_count=1)
    assert c.model_dump()["index"] == 2
