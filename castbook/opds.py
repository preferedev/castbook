"""OPDS 1.2 catalog — lets e-reader/audiobook apps browse the library."""

from __future__ import annotations

from urllib.parse import quote
from xml.sax.saxutils import escape

from .artifacts import ChaptersFile, load_artifact
from .config import Settings


def build_catalog(cfg: Settings, base_url: str, token: str | None = None) -> str:
    base = base_url.rstrip("/")
    qs = f"?token={quote(token)}" if token else ""
    entries: list[str] = []
    if cfg.data_dir.exists():
        for d in sorted(cfg.data_dir.iterdir()):
            if not d.is_dir():
                continue
            ch = load_artifact(ChaptersFile, d)
            if ch is None:
                continue
            m = ch.meta
            bid = d.name
            links = [
                f'<link rel="http://opds-spec.org/image" href="{base}/api/books/{bid}/cover{qs}"/>',
                f'<link rel="subsection" type="application/atom+xml" '
                f'href="{base}/api/books/{bid}/feed.xml{qs}"/>',
            ]
            for f in sorted((d / "export").glob("*")) if (d / "export").is_dir() else []:
                if not f.is_file():
                    continue
                mime = {
                    ".m4b": "audio/mp4",
                    ".mp3": "audio/mpeg",
                    ".zip": "application/zip",
                    ".epub": "application/epub+zip",
                }.get(f.suffix.lower())
                if mime:
                    href = f"{base}/api/books/{bid}/download/{quote(f.name)}{qs}"
                    links.append(
                        f'<link rel="http://opds-spec.org/acquisition" type="{mime}" '
                        f'title="{escape(f.name)}" href="{href}"/>'
                    )
            entries.append(
                "<entry>"
                f"<id>urn:castbook:{escape(bid)}</id>"
                f"<title>{escape(m.title)}</title>"
                f"<author><name>{escape(m.author)}</name></author>"
                f'<content type="text">{len(ch.chapters)} chapters · '
                f"{sum(c.word_count for c in ch.chapters)} words</content>"
                + "".join(links)
                + "</entry>"
            )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">'
        "<id>urn:castbook:catalog</id><title>Castbook library</title>"
        + "".join(entries)
        + "</feed>"
    )
