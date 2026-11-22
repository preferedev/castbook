from pathlib import Path

from castbook.parse import txt


def test_markdown_headings_split(tmp_path: Path) -> None:
    p = tmp_path / "b.txt"
    p.write_text("# Chapter One\n\n" + "words " * 50 + "\n\n# Chapter Two\n\n" + "more " * 50)
    _, chapters = txt.parse(p)
    assert len(chapters) == 2
    assert chapters[0].title == "Chapter One"
    assert chapters[1].index == 1


def test_no_headings_single_chapter(tmp_path: Path) -> None:
    p = tmp_path / "b.txt"
    p.write_text("just prose " * 30)
    _, chapters = txt.parse(p)
    assert len(chapters) == 1


def test_front_matter_becomes_first_chapter(tmp_path: Path) -> None:
    p = tmp_path / "b.txt"
    p.write_text("Title\n\nby Someone\n\nCHAPTER I\n\n" + "body " * 60)
    _, chapters = txt.parse(p)
    assert len(chapters) == 2
    assert chapters[0].title == "Front matter"
    assert chapters[1].title == "Chapter I"
