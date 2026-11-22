"""Ad-hoc 'hear it now' reader: pasted text or a URL synthesized as chunks."""

import re

MAX_READ_CHARS = 200_000
CHUNK_CHARS = 1500


def article_text(html: str) -> str:
    """Readable body text from a web page."""
    from bs4 import BeautifulSoup, Tag

    soup = BeautifulSoup(html, "html.parser")
    for t in soup.select("script,style,nav,header,footer,aside,form,iframe,svg"):
        t.decompose()
    root = soup.find("article") or soup.find("main") or soup.body
    if not isinstance(root, Tag):
        return soup.get_text("\n", strip=True)
    paras = [p.get_text(" ", strip=True) for p in root.find_all("p")]
    paras = [p for p in paras if len(p) > 40]
    return "\n\n".join(paras) or root.get_text("\n", strip=True)


def split_for_reading(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aware chunks for sequential TTS playback."""
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    out: list[str] = []
    buf = ""
    for p in paras:
        while len(p) > max_chars:
            cut = p.rfind(". ", 0, max_chars + 2)
            cut = cut + 1 if cut >= max_chars // 2 else max_chars
            seg, p = p[:cut].strip(), p[cut:].strip()
            if seg:
                if buf:
                    out.append(buf)
                    buf = ""
                out.append(seg)
        if buf and len(buf) + len(p) + 2 > max_chars:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        out.append(buf)
    return out
