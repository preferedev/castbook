"""EPUB → (BookMeta, chapters) via ebooklib spine/TOC.

Chapter detection order: TOC entries → spine-item boundaries → length split.
"""

from __future__ import annotations

from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup, Tag
from ebooklib import epub as el_epub

from ..artifacts import BookMeta, Chapter
from .txt import split_by_words

MIN_WORDS = 40
MAX_WORDS = 4000


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    book = el_epub.read_epub(str(path), options={"ignore_ncx": False})
    meta = _meta(book, path, cover_dir)
    chapters = _chapters(book)
    return meta, chapters


def _meta(book: el_epub.EpubBook, path: Path, cover_dir: Path | None) -> BookMeta:
    def dc(name: str) -> str:
        values = book.get_metadata("DC", name)
        return str(values[0][0]).strip() if values else ""

    cover_path = None
    if cover_dir is not None:
        cover_dir.mkdir(parents=True, exist_ok=True)
        for item in book.get_items_of_type(ebooklib.ITEM_COVER):
            cover_path = f"cover{Path(item.get_name()).suffix or '.jpg'}"
            _write_cover(cover_dir / cover_path, item.get_content())
            break
        if cover_path is None:
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                if "cover" in item.get_name().lower():
                    cover_path = f"cover{Path(item.get_name()).suffix or '.jpg'}"
                    _write_cover(cover_dir / cover_path, item.get_content())
                    break

    return BookMeta(
        title=dc("title") or path.stem.replace("_", " ").title(),
        author=dc("creator") or "Unknown",
        language=dc("language") or "en",
        source_file=path.name,
        cover_path=cover_path,
    )


def _write_cover(dest: Path, content: str | bytes) -> None:
    dest.write_bytes(content.encode() if isinstance(content, str) else content)


def _item_text(item: object) -> str:
    soup = BeautifulSoup(item.get_content(), "lxml")  # type: ignore[attr-defined]
    for bad in soup.select("script, style, nav, sup"):
        bad.decompose()
    blocks: list[str] = []
    body = soup.find("body")
    root = body if isinstance(body, Tag) else soup
    for el in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p"]):
        line = " ".join(el.get_text(" ", strip=True).split())
        if line:
            blocks.append(line)
    return "\n\n".join(blocks)


def _chapters(book: el_epub.EpubBook) -> list[Chapter]:
    docs = {i.get_id(): i for i in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
    ordered = [docs[idref] for idref, _linear in book.spine if idref in docs]
    ordered += [d for i, d in docs.items() if d not in ordered]
    toc_titles = _toc_map(book)

    raw: list[Chapter] = []
    for item in ordered:
        text = _item_text(item)
        if len(text.split()) < MIN_WORDS:
            continue
        name = item.get_name()
        raw.append(
            Chapter(
                index=len(raw),
                title=toc_titles.get(name, ""),
                text=text,
                word_count=len(text.split()),
                source={"href": name},
            )
        )

    merged = _merge_stubs(raw)
    split = [c for ch in merged for c in _split_long(ch)]
    for i, ch in enumerate(split):
        ch.index = i
        if not ch.title:
            ch.title = f"Chapter {i + 1}"
    return split


def _toc_map(book: el_epub.EpubBook) -> dict[str, str]:
    """TOC href → title, so spine items pick up real chapter names."""
    out: dict[str, str] = {}
    nodes = list(book.toc)

    def walk(entries: list[object]) -> None:
        for e in entries:
            if isinstance(e, tuple) and len(e) == 2:
                children = e[1]
                if isinstance(children, (list, tuple)):
                    walk(list(children))
                continue
            href = getattr(e, "href", "") or ""
            title = getattr(e, "title", "") or ""
            if href and title:
                out[href.split("#")[0]] = title.strip()

    walk(nodes)
    return out


def _merge_stubs(chapters: list[Chapter]) -> list[Chapter]:
    """Front-matter stubs (title page, copyright) merge forward."""
    if not chapters:
        return []
    body_at = next(
        (i for i, c in enumerate(chapters) if c.word_count >= 250),
        len(chapters) - 1,
    )
    out: list[Chapter] = []
    for i, ch in enumerate(chapters):
        if i < body_at and out:
            continue
        if i < body_at and not out:
            out.append(ch)
            continue
        if ch.word_count < MIN_WORDS * 4 and out:
            out[-1].text += "\n\n" + ch.text
            out[-1].word_count += ch.word_count
            continue
        out.append(ch)
    return out


def _split_long(chapter: Chapter) -> list[Chapter]:
    if chapter.word_count <= MAX_WORDS:
        return [chapter]
    parts = split_by_words(chapter.text, MAX_WORDS)
    return [
        Chapter(
            index=chapter.index,
            title=chapter.title if i == 0 else f"{chapter.title} (cont.)",
            text=p,
            word_count=len(p.split()),
            source=chapter.source,
        )
        for i, p in enumerate(parts)
    ]
