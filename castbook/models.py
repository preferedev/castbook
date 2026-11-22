"""Model download manager — manifest-driven, resumable, hash-verified.

Every entry carries its license string; `pull` refuses silently-skipped
licenses because the manifest is the disclosure, not a prompt.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

import httpx

from .artifacts import ModelSpec

MANIFEST: list[ModelSpec] = [
    ModelSpec(
        id="qwen3-4b-q4",
        kind="llm",
        url=(
            "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/"
            "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
        ),
        filename="Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
        size_bytes=2_500_000_000,
        sha256="3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
        license="Apache-2.0",
        required=False,
    ),
    ModelSpec(
        id="kokoro-v1",
        kind="tts",
        url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
        filename="kokoro-v1.0.onnx",
        size_bytes=325_533_000,
        sha256="7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
        license="Apache-2.0",
        required=True,
    ),
    ModelSpec(
        id="kokoro-voices-v1",
        kind="tts",
        url="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
        filename="voices-v1.0.bin",
        size_bytes=26_700_000,
        sha256="bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
        license="Apache-2.0",
        required=True,
    ),
]

CHUNK = 1 << 20


def find(spec_id: str) -> ModelSpec | None:
    return next((m for m in MANIFEST if m.id == spec_id), None)


def resolve_model(models_dir: Path, spec_id: str) -> Path | None:
    """Local path of a downloaded model, or None."""
    spec = find(spec_id)
    if spec is None:
        return None
    path = models_dir / spec.filename
    return path if path.exists() else None


def pull(
    models_dir: Path, ids: list[str] | None = None, log: Callable[[str], None] = print
) -> list[Path]:
    models_dir.mkdir(parents=True, exist_ok=True)
    specs = [s for s in MANIFEST if ids is None or s.id in ids]
    missing = [i for i in (ids or []) if find(i) is None]
    if missing:
        raise ValueError(f"unknown models: {', '.join(missing)}")
    downloaded: list[Path] = []
    for spec in specs:
        dest = models_dir / spec.filename
        if dest.exists() and _hash_ok(dest, spec):
            log(f"[models] {spec.id} already present ({spec.license})")
            downloaded.append(dest)
            continue
        log(f"[models] {spec.id} — {spec.size_bytes / 1e6:.0f} MB — license {spec.license}")
        _download(spec.url, dest)
        if not _hash_ok(dest, spec):
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"hash mismatch on {spec.id}; deleted partial file")
        downloaded.append(dest)
    return downloaded


def _hash_ok(path: Path, spec: ModelSpec) -> bool:
    if not spec.sha256:
        return True
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest() == spec.sha256


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        mode = "ab" if have and r.status_code == 206 else "wb"
        if mode == "wb":
            have = 0
        total = int(r.headers.get("content-length", 0)) + have
        with tmp.open(mode) as f:
            for chunk in r.iter_bytes(CHUNK):
                f.write(chunk)
                have += len(chunk)
                if total:
                    pct = have * 100 // total
                    sys.stderr.write(f"\r  {have / 1e6:.0f}/{total / 1e6:.0f} MB {pct}%")
        sys.stderr.write("\n")
    tmp.replace(dest)
