"""Outbound HTTP helpers with SSRF guards."""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_UPLOAD = 200 * 1024 * 1024


def supported_suffixes() -> tuple[str, ...]:
    from .parse import PARSERS

    return tuple(PARSERS)


class FetchError(Exception):
    """A URL could not be fetched or is not allowed."""

    def __init__(self, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.status = status


def assert_public_host(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
        addrs = [ip]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(i[4][0]) for i in socket.getaddrinfo(host, None)]
        except (socket.gaierror, ValueError) as e:
            raise FetchError(f"cannot resolve host {host}", status=502) from e
    if not addrs or not all(a.is_global for a in addrs):
        raise FetchError("url host is not public")


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> Any:
        if not newurl.lower().startswith(("http://", "https://")):
            raise FetchError("redirect to unsupported scheme")
        assert_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirect())


def open_url(url: str, timeout: float = 60) -> Any:
    """Open a public http(s) URL; raises FetchError on non-public hosts."""
    assert_public_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": "castbook/0.1"})
    try:
        return _opener.open(req, timeout=timeout)
    except urllib.error.URLError as e:
        raise FetchError(f"fetch failed: {e.reason}", status=502) from e


def assert_public_peer(resp: Any, url: str) -> None:
    """Verify the actually-connected peer IP is public — DNS can rebind
    between the assert_public_host check and connect() (TOCTOU). Skipped
    when a configured proxy carries the request: the peer is the proxy."""
    parsed = urllib.parse.urlparse(url)
    # mirror urllib's ProxyHandler exactly: scheme key only, bypass on netloc
    if urllib.request.getproxies().get(parsed.scheme) and not urllib.request.proxy_bypass(
        parsed.netloc
    ):
        return
    sock = getattr(getattr(resp.fp, "raw", None), "_sock", None)
    if sock is not None:
        ip = ipaddress.ip_address(sock.getpeername()[0])
        if not ip.is_global:
            raise FetchError("url resolved to a non-public address")


def fetch_book_url(url: str, tmp_dir: Path, max_size: int = MAX_UPLOAD) -> Path:
    """Download an ebook URL into tmp_dir; raises FetchError."""
    if not url.lower().startswith(("http://", "https://")):
        raise FetchError("url must start with http:// or https://")
    resp = open_url(url)
    with resp:
        assert_public_peer(resp, resp.geturl())
        name = Path(urllib.parse.urlparse(resp.geturl()).path).name or "book.epub"
        suffix = Path(name).suffix.lower()
        if suffix not in supported_suffixes():
            raise FetchError(f"unsupported format {suffix or '(none)'}")
        tmp_path = tmp_dir / name
        size = 0
        with tmp_path.open("wb") as out:
            while chunk := resp.read(1 << 20):
                size += len(chunk)
                if size > max_size:
                    tmp_path.unlink(missing_ok=True)
                    raise FetchError("file too large", status=413)
                out.write(chunk)
    return tmp_path
