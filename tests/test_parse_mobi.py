import struct
from pathlib import Path

import pytest

from castbook.parse import parse


def _mobi(text: bytes, compression: int = 1, encryption: int = 0) -> bytes:
    head = bytearray(512)
    struct.pack_into(">H H I H H H", head, 0, compression, 0, len(text), 1, 4096, encryption)
    head[16:20] = b"MOBI"
    struct.pack_into(">I", head, 20, 0xE4)
    struct.pack_into(">I", head, 28, 65001)
    name = b"Test Book"
    struct.pack_into(">I I", head, 0x54, 0x100, len(name))
    head[0x100 : 0x100 + len(name)] = name
    header = bytearray(78 + 16)
    header[0:4] = b"TstB"
    header[60:64] = b"BOOK"
    header[64:68] = b"MOBI"
    struct.pack_into(">H", header, 76, 2)
    off0 = len(header)
    off1 = off0 + len(head)
    struct.pack_into(">I", header, 78, off0)
    struct.pack_into(">I", header, 86, off1)
    return bytes(header + head) + text


def test_mobi_uncompressed(tmp_path: Path) -> None:
    body = b"<p>CHAPTER 1</p><p>" + b"words " * 40 + b"</p><p>CHAPTER 2</p><p>more</p>"
    p = tmp_path / "b.mobi"
    p.write_bytes(_mobi(body))
    meta, chapters = parse(p)
    assert meta.title == "Test Book"
    assert len(chapters) >= 1
    assert "words" in chapters[0].text


def test_mobi_palmdoc_compressed(tmp_path: Path) -> None:
    plain = b"<p>hello world hello world hello world</p>"
    packed = bytearray()
    i = 0
    while i < len(plain):
        packed.append(1)
        packed.append(plain[i])
        i += 1
    p = tmp_path / "b.mobi"
    p.write_bytes(_mobi(bytes(packed), compression=2))
    _, chapters = parse(p)
    assert "hello world" in chapters[0].text


def test_mobi_drm_rejected(tmp_path: Path) -> None:
    p = tmp_path / "b.mobi"
    p.write_bytes(_mobi(b"x" * 100, encryption=1))
    with pytest.raises(ValueError, match="DRM"):
        parse(p)


def test_mobi_huffcdic_rejected(tmp_path: Path) -> None:
    p = tmp_path / "b.mobi"
    p.write_bytes(_mobi(b"x" * 100, compression=17480))
    with pytest.raises(ValueError, match="HUFF/CDIC"):
        parse(p)
