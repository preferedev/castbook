"""MOBI / AZW3 → chapters.

Minimal in-repo PalmDB + PalmDOC reader: every existing MOBI library is
GPL/AGPL, which conflicts with the Apache/MIT-only dependency rule, so the
container format is handled here directly. Supported: uncompressed and
PalmDOC-compressed text records, UTF-8 or CP1252. HUFF/CDIC records and any
DRM raise a clear error — DRM is out of scope by design.
"""

from __future__ import annotations

import html
import re
import struct
from pathlib import Path

from ..artifacts import BookMeta, Chapter
from .txt import chapters_from_text

_HUFFCDIC = 17480
_ENC = {1252: "cp1252", 65001: "utf-8"}
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


def parse(path: Path, cover_dir: Path | None = None) -> tuple[BookMeta, list[Chapter]]:
    _ = cover_dir
    data = path.read_bytes()
    records = _records(data)
    head = records[0]

    # PalmDOC header: compression(2), unused(2), text_length(4), record_count(2),
    # record_size(2), encryption_type(2), unknown(2)
    compression, _unused, _text_len, count, _size, enc_type = struct.unpack(
        ">H H I H H H", head[:14]
    )
    if enc_type:
        raise ValueError("MOBI file is DRM-encrypted; Castbook does not break DRM")
    if compression == _HUFFCDIC:
        raise ValueError("MOBI uses HUFF/CDIC compression, which is unsupported — convert to EPUB")
    if compression not in (1, 2):
        raise ValueError(f"unknown MOBI compression type {compression}")

    encoding = _ENC.get(_u32(head, 28), "utf-8")
    title = _exth(head, 503) or _fullname(head) or path.stem.replace("_", " ").title()
    author = _exth(head, 100) or "Unknown"

    extra_flags = _u16(head, 16 + 0xF2) if len(head) > 16 + 0xF2 + 2 else 0
    raw = b"".join(
        _strip_trailer(records[i]) if extra_flags else records[i]
        for i in range(1, min(count + 1, len(records)))
    )
    if compression == 2:
        raw = _palmdoc(raw)
    text = _html_to_text(raw.decode(encoding, errors="replace"))

    meta = BookMeta(title=title, source_file=path.name, author=author)
    return meta, chapters_from_text(text)


def _records(data: bytes) -> list[bytes]:
    if len(data) < 78:
        raise ValueError("not a MOBI file (truncated header)")
    count = struct.unpack(">H", data[76:78])[0]
    offsets = [struct.unpack(">I", data[78 + 8 * i : 82 + 8 * i])[0] for i in range(count)]
    out = []
    for i, off in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < len(offsets) else len(data)
        out.append(data[off:end])
    if not out:
        raise ValueError("MOBI file has no records")
    return out


def _u16(buf: bytes, off: int) -> int:
    return int(struct.unpack(">H", buf[off : off + 2])[0])


def _u32(buf: bytes, off: int) -> int:
    return int(struct.unpack(">I", buf[off : off + 4])[0])


def _fullname(head: bytes) -> str:
    if len(head) < 0x5C:
        return ""
    off, length = _u32(head, 0x54), _u32(head, 0x58)
    if off and length and off + length <= len(head):
        return head[off : off + length].decode("utf-8", errors="replace").strip()
    return ""


def _exth(head: bytes, rec_type: int) -> str | None:
    if len(head) < 16 + 0x84 or head[16:20] != b"MOBI":
        return None
    mobi_len = _u32(head, 20)
    flags = _u32(head, 16 + 0x80)
    if not flags & 0x40:
        return None
    pos = 16 + mobi_len
    if head[pos : pos + 4] != b"EXTH":
        return None
    exth_len = _u32(head, pos + 4)
    n = _u32(head, pos + 8)
    p = pos + 12
    for _ in range(n):
        rtype, rlen = _u32(head, p), _u32(head, p + 4)
        if rtype == rec_type:
            return head[p + 8 : p + rlen].decode("utf-8", errors="replace").strip()
        p += rlen
        if p >= pos + exth_len:
            break
    return None


def _strip_trailer(rec: bytes) -> bytes:
    if not rec:
        return rec
    n = rec[-1] & 0xFF
    return rec[: -(n + 1)] if 0 < n < 9 else rec


def _palmdoc(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        c = data[i]
        i += 1
        if c == 0:
            out.append(c)
        elif c <= 8:
            out += data[i : i + c]
            i += c
        elif c <= 0x7F:
            out.append(c)
        elif c <= 0xBF:
            if i >= len(data):
                break
            pair = (c << 8) | data[i]
            i += 1
            dist, length = (pair >> 3) & 0x7FF, (pair & 7) + 3
            for _ in range(length):
                out.append(out[-dist])
        else:
            out += b" " + bytes([c ^ 0x80])
    return bytes(out)


def _html_to_text(markup: str) -> str:
    markup = re.sub(r"(?i)</(p|div|h[1-6]|li|blockquote|tr)\s*>", "\n\n", markup)
    markup = re.sub(r"(?i)<(br|hr)\s*/?\s*>", "\n", markup)
    text = html.unescape(_TAG.sub("", markup))
    return "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines())
