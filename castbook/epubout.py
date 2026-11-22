"""EPUB 3 media-overlay export — the audiobook inside the ebook.

Read-aloud in Thorium, Apple Books, Google Play Books: each unit is a
highlightable <par> synced to a clip of the chapter audio.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .artifacts import (
    AttributionFile,
    AudioManifest,
    ChaptersFile,
    ChapterStatus,
    UnitStatus,
    load_artifact,
)
from .audio.pacing import pause_after
from .workdir import BookPaths

_CONTAINER = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>'
)


def _smil_time(s: float) -> str:
    ms = round(s * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s_, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s_:02d}.{ms:03d}"


def build_media_epub(book: BookPaths, out: Path) -> Path:
    """Zip an EPUB3 with smil overlays over the rendered chapter audio.

    Chapters without rendered audio ship text-only. Returns `out`.
    """
    ch = load_artifact(ChaptersFile, book.dir)
    attrib = load_artifact(AttributionFile, book.dir)
    manifest = load_artifact(AudioManifest, book.dir)
    if ch is None:
        raise FileNotFoundError("no chapters — import first")
    units_by_ch: dict[int, list[Any]] = {}
    for u in attrib.units if attrib else []:
        units_by_ch.setdefault(u.chapter, []).append(u)

    m = ch.meta
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "META-INF").mkdir()
        (root / "OEBPS" / "audio").mkdir(parents=True)
        (root / "mimetype").write_text("application/epub+zip")
        (root / "META-INF" / "container.xml").write_text(_CONTAINER)

        manifest_items: list[str] = []
        spine: list[str] = []
        durations: list[tuple[str, float]] = []
        total = 0.0
        for c in ch.chapters:
            cid = f"ch{c.index:03d}"
            wav = book.audio / f"{cid}.wav"
            units = [
                u
                for u in units_by_ch.get(c.index, [])
                if manifest
                and manifest.units.get(u.id)
                and manifest.units[u.id].status == UnitStatus.done
                and manifest.chapters.get(str(c.index), None)
                and manifest.chapters[str(c.index)].status == ChapterStatus.done
            ]
            audio_rel = ""
            if wav.exists() and units:
                mp3 = root / "OEBPS" / "audio" / f"{cid}.mp3"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-i",
                        str(wav),
                        "-codec:a",
                        "libmp3lame",
                        "-q:a",
                        "4",
                        str(mp3),
                    ],
                    check=True,
                )
                audio_rel = f"audio/{cid}.mp3"
                manifest_items.append(
                    f'<item id="au-{cid}" href="{audio_rel}" media-type="audio/mpeg"/>'
                )
                manifest_items.append(
                    f'<item id="smil-{cid}" href="{cid}.smil" media-type="application/smil+xml"/>'
                )

            pars, t, prev = [], 0.0, None
            body_parts = []
            for u in units_by_ch.get(c.index, []):
                body_parts.append(f'<p id="u-{u.id}">{escape(u.text)}</p>')
                entry = manifest.units.get(u.id) if manifest else None
                if u not in units or entry is None:
                    continue
                if prev is not None:
                    t += pause_after(prev, u)
                pars.append(
                    f'<par id="p-{u.id}"><text src="{cid}.xhtml#u-{u.id}"/>'
                    f'<audio src="{audio_rel}" clipBegin="{_smil_time(t)}" '
                    f'clipEnd="{_smil_time(t + entry.duration_s)}"/></par>'
                )
                t += entry.duration_s
                prev = u
            if not body_parts:
                for para in c.text.split("\n\n"):
                    if para.strip():
                        body_parts.append(f"<p>{escape(para.strip())}</p>")
            xhtml = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<html xmlns="http://www.w3.org/1999/xhtml" '
                'xmlns:epub="http://www.idpf.org/2007/ops">'
                f"<head><title>{escape(c.title)}</title></head><body>"
                f"<h1>{escape(c.title)}</h1>" + "".join(body_parts) + "</body></html>"
            )
            (root / "OEBPS" / f"{cid}.xhtml").write_text(xhtml)
            if audio_rel:
                smil = (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<smil xmlns="http://www.w3.org/ns/SMIL" '
                    'xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">'
                    f"<body>{''.join(pars)}</body></smil>"
                )
                (root / "OEBPS" / f"{cid}.smil").write_text(smil)
                durations.append((f"smil-{cid}", t))
                total += t
            overlay = f' media-overlay="smil-{cid}"' if audio_rel else ""
            manifest_items.append(
                f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"{overlay}/>'
            )
            spine.append(f'<itemref idref="{cid}"/>')

        cover = next(
            (f for base in (book.dir, book.source) for f in sorted(base.glob("cover.*"))),
            None,
        )
        cover_item = ""
        if cover is not None and cover.exists():
            ext = cover.suffix.lower().lstrip(".") or "jpg"
            dest = root / "OEBPS" / f"cover.{ext}"
            shutil.copy2(cover, dest)
            mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(
                ext, "image/jpeg"
            )
            cover_item = (
                f'<item id="cover" href="cover.{ext}" media-type="{mime}" '
                'properties="cover-image"/>'
            )

        nav = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head>'
            '<body><nav epub:type="toc"><ol>'
            + "".join(
                f'<li><a href="ch{c.index:03d}.xhtml">{escape(c.title)}</a></li>'
                for c in ch.chapters
            )
            + "</ol></nav></body></html>"
        )
        (root / "OEBPS" / "nav.xhtml").write_text(nav)

        dur_meta = (
            "".join(
                f'<meta property="media:duration" refines="#{sid}">{_smil_time(t)}</meta>'
                for sid, t in durations
            )
            + f'<meta property="media:duration">{_smil_time(total)}</meta>'
        )
        opf = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="bid">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:identifier id="bid">urn:castbook:{escape(ch.book_id)}</dc:identifier>'
            f"<dc:title>{escape(m.title)}</dc:title>"
            f"<dc:creator>{escape(m.author)}</dc:creator>"
            f"<dc:language>{escape(m.language)}</dc:language>"
            '<meta property="dcterms:modified">2026-01-01T00:00:00Z</meta>'
            '<meta property="media:active-class">-epub-media-overlay-active</meta>'
            f"{dur_meta}</metadata>"
            "<manifest>"
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            + cover_item
            + "".join(manifest_items)
            + "</manifest>"
            f"<spine>{''.join(spine)}</spine></package>"
        )
        (root / "OEBPS" / "content.opf").write_text(opf)

        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w") as z:
            z.write(root / "mimetype", "mimetype", zipfile.ZIP_STORED)
            for f in sorted(root.rglob("*")):
                if f.is_file() and f.name != "mimetype":
                    z.write(f, f.relative_to(root), zipfile.ZIP_DEFLATED)
    return out
