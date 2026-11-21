"""Analyze resume: re-running reuses attributed chapters and the cast."""

from pathlib import Path

from castbook import analyze
from castbook.analyze.attributor import Attributor
from castbook.artifacts import BookMeta, Chapter, ChaptersFile, Character, Unit, save_artifact
from castbook.config import Settings
from castbook.workdir import BookPaths


class CountingAttributor(Attributor):
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def extract_cast(self, chapters: list[Chapter]) -> list[Character]:
        return [Character(id="hero", name="Hero")]

    def attribute(self, chapter: Chapter, cast: list[Character]) -> list[Unit]:
        self.calls += 1
        return [
            Unit(
                id=f"ch{chapter.index:03d}-u0000",
                chapter=chapter.index,
                kind="dialogue",
                text="hi",
                speaker="hero",
            )
        ]


def _book(tmp_path: Path, n: int = 3) -> BookPaths:
    book = BookPaths(tmp_path, "b1")
    book.ensure()
    chapters = [
        Chapter(index=i, title=f"c{i}", text=f"chapter {i} text", word_count=3) for i in range(n)
    ]
    save_artifact(
        ChaptersFile(
            book_id="b1",
            meta=BookMeta(title="t", author="a", source_file="x.txt"),
            chapters=chapters,
            input_hash="h",
        ),
        book.dir,
    )
    return book


def test_analyze_resume_skips_done_chapters(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    book = _book(tmp_path)
    cfg = Settings(data_dir=tmp_path)
    fake = CountingAttributor()
    monkeypatch.setattr(analyze, "make_attributor", lambda c, log=print: fake)

    analyze.run(book, cfg)
    assert fake.calls == 3

    again = CountingAttributor()
    monkeypatch.setattr(analyze, "make_attributor", lambda c, log=print: again)
    analyze.run(book, cfg)
    assert again.calls == 0


def test_analyze_resume_partial(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    book = _book(tmp_path)
    cfg = Settings(data_dir=tmp_path)
    fake = CountingAttributor()
    monkeypatch.setattr(analyze, "make_attributor", lambda c, log=print: fake)
    analyze.run(book, cfg)

    # extend the book with a new chapter → same input_hash won't match, so
    # simulate a mid-run checkpoint instead: only chapter 0 attributed
    from castbook.artifacts import AttributionFile
    from castbook.artifacts import save_artifact as save

    save(
        AttributionFile(
            book_id="b1",
            attributor="counting",
            units=[
                Unit(
                    id="ch000-u0000",
                    chapter=0,
                    kind="dialogue",
                    text="hi",
                    speaker="hero",
                )
            ],
            input_hash="h",
        ),
        book.dir,
    )
    again = CountingAttributor()
    monkeypatch.setattr(analyze, "make_attributor", lambda c, log=print: again)
    analyze.run(book, cfg)
    assert again.calls == 2  # only chapters 1,2 attributed
