"""Export — M4B (AAC + chapters + cover) and per-chapter MP3 via ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..artifacts import BookMeta


def _ffmpeg(args: list[str]) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[:500]}")


def _concat_file(chapters: list[Path]) -> Path:
    lst = chapters[0].parent / ".concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in chapters))
    return lst


def mux_m4b(
    chapter_wavs: list[Path],
    titles: list[str],
    meta: BookMeta,
    out: Path,
    workdir: Path,
) -> Path:
    if not chapter_wavs:
        raise ValueError("no chapters to mux")
    cover = workdir / meta.cover_path if meta.cover_path else None

    durations = [float(_probe_duration(p)) for p in chapter_wavs]
    meta_file = workdir / ".ffmetadata"
    lines = [
        ";FFMETADATA1",
        f"title={_esc(meta.title)}",
        f"artist={_esc(meta.author)}",
        f"album={_esc(meta.title)}",
        "genre=Audiobook",
    ]
    start = 0.0
    for i, (title, dur) in enumerate(zip(titles, durations, strict=True)):
        end = start + dur * 1000
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(start)}",
            f"END={int(end)}",
            f"title={_esc(title or f'Chapter {i + 1}')}",
        ]
        start = end
    meta_file.write_text("\n".join(lines) + "\n")

    concat = _concat_file(chapter_wavs)
    tmp = out.with_suffix(".tmp.m4b")
    args = [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat),
        "-i",
        str(meta_file),
        "-map_metadata",
        "1",
        "-map_chapters",
        "1",
    ]
    if cover and cover.exists():
        args += [
            "-i",
            str(cover),
            "-map",
            "0:a",
            "-map",
            "2:v",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-c:v",
            "copy",
            "-disposition:v:0",
            "attached_pic",
        ]
    else:
        args += ["-vn", "-c:a", "aac", "-b:a", "96k"]
    args += ["-f", "mp4", str(tmp)]
    _ffmpeg(args)
    tmp.replace(out)
    return out


def export_mp3(chapter_wavs: list[Path], titles: list[str], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    m3u: list[str] = []
    for i, (wav, title) in enumerate(zip(chapter_wavs, titles, strict=True)):
        name = f"{i + 1:02d} - {_safe(title or f'Chapter {i + 1}')}.mp3"
        _ffmpeg(
            [
                "-i",
                str(wav),
                "-c:a",
                "libmp3lame",
                "-b:a",
                "128k",
                "-metadata",
                f"title={title}",
                str(out_dir / name),
            ]
        )
        m3u.append(name)
    (out_dir / "playlist.m3u").write_text("\n".join(m3u) + "\n")
    return out_dir


def _probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"ffprobe failed on {path}: {r.stderr.strip()[:200]}") from None


def _esc(s: str) -> str:
    s = s.replace("\\", "\\\\")
    for ch in "=;#":
        s = s.replace(ch, "\\" + ch)
    return s


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in " ._-" else "_" for c in s).strip() or "chapter"
