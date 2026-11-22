"""FictionBook (.fb2) parsing — stdlib XML only."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..artifacts import BookMeta, Chapter
from .txt import chapters_from_text

NS = "{http://www.gribuser.ru/xml/fictionbook/2.0}"


def _text_of(el: ET.Element) -> str:
    return "".join(el.itertext())


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    _ = cover_dir
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"bad fb2: {e}") from None
    ns = NS if root.tag.startswith(NS) else ""
    info = root.find(f"{ns}description/{ns}title-info")
    title = path.stem.replace("_", " ").title()
    author = ""
    if info is not None:
        t = info.find(f"{ns}book-title")
        if t is not None and (t.text or "").strip():
            title = (t.text or "").strip()
        a = info.find(f"{ns}author")
        if a is not None:
            parts = [a.findtext(f"{ns}first-name") or "", a.findtext(f"{ns}last-name") or ""]
            author = " ".join(p.strip() for p in parts if p and p.strip())
    chapters: list[Chapter] = []
    body = root.find(f"{ns}body")
    if body is not None:
        for i, section in enumerate(body.iter(f"{ns}section")):
            title_el = section.find(f"{ns}title")
            ch_title = _text_of(title_el).strip() if title_el is not None else f"Chapter {i + 1}"
            title_ps = {id(p) for p in title_el.iter(f"{ns}p")} if title_el is not None else set()
            paras = [
                _text_of(p).strip()
                for p in section.iter(f"{ns}p")
                if _text_of(p).strip() and id(p) not in title_ps
            ]
            text = "\n\n".join(paras)
            if text:
                chapters.extend(chapters_from_text(ch_title + "\n\n" + text))
    if not chapters:
        # flat body without sections, or unusual nesting — take all <p>
        paras = [_text_of(p).strip() for p in root.iter(f"{ns}p") if _text_of(p).strip()]
        chapters = chapters_from_text("\n\n".join(paras))
    meta = BookMeta(title=title, author=author, source_file=path.name, language="")
    return meta, chapters
