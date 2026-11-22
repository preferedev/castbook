"""Per-book RSS feed so podcast/audiobook apps can subscribe and stream chapters."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from typing import Any

from .artifacts import (
    AttributionFile,
    AudioManifest,
    ChaptersFile,
    UnitStatus,
    load_artifact,
)


def build_feed(book_dir: Path, base_url: str) -> str | None:
    """RSS 2.0 feed with one <item> per rendered chapter; None if nothing rendered."""
    ch = load_artifact(ChaptersFile, book_dir)
    attrib = load_artifact(AttributionFile, book_dir)
    manifest = load_artifact(AudioManifest, book_dir)
    if ch is None or attrib is None or manifest is None:
        return None
    ch_by_id = {u.id: u.chapter for u in attrib.units}
    rendered = sorted(
        {
            ch_by_id[u]
            for u, e in manifest.units.items()
            if e.status == UnitStatus.done and u in ch_by_id
        }
    )
    if not rendered:
        return None
    base = base_url.rstrip("/")
    bid = ch.book_id
    meta = ch.meta
    title = escape(meta.title or bid)
    items = []
    for i in rendered:
        c = next((c for c in ch.chapters if c.index == i), None)
        if c is None:
            continue
        wav = book_dir / "audio" / f"ch{i:03d}.wav"
        if not wav.exists():
            continue
        mtime = wav.stat().st_mtime
        items.append(
            f"""    <item>
      <title>{escape(c.title or f"Chapter {i}")}</title>
      <enclosure url="{base}/api/books/{escape(bid)}/chapters/{i}/audio"
        type="audio/wav" length="{wav.stat().st_size}"/>
      <guid isPermaLink="false">{escape(bid)}-ch{i}</guid>
      <pubDate>{format_datetime(datetime.fromtimestamp(mtime, timezone.utc))}</pubDate>
      <itunes:order>{i}</itunes:order>
    </item>"""
        )
    if not items:
        return None
    cover = f"{base}/api/books/{escape(bid)}/cover"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>{title}</title>
    <link>{base}/reader/{escape(bid)}</link>
    <description>{escape(meta.author)} — read by castbook</description>
    <language>{escape(meta.language)}</language>
    <itunes:author>{escape(meta.author)}</itunes:author>
    <itunes:image href="{cover}"/>
    <image><url>{cover}</url><title>{title}</title><link>{base}</link></image>
{chr(10).join(items)}
  </channel>
</rss>
"""


def feed_dict(book_dir: Path) -> dict[str, Any]:
    """Debug helper: which chapters the feed would contain."""
    attrib = load_artifact(AttributionFile, book_dir)
    manifest = load_artifact(AudioManifest, book_dir)
    if not attrib or not manifest:
        return {"rendered": []}
    ch_by_id = {u.id: u.chapter for u in attrib.units}
    return {
        "rendered": sorted(
            {
                ch_by_id[u]
                for u, e in manifest.units.items()
                if e.status == UnitStatus.done and u in ch_by_id
            }
        )
    }
