"""Attribution eval: run the pipeline's attributor over labeled excerpts and
score speaker-accuracy. Usage: `python -m eval.run` → eval/report.md.

Gold format — eval/gold/<name>.json:
{
  "title": "...",
  "text": "<chapter text>",
  "cast": [{"name": "Elizabeth", "aliases": ["Lizzy"], "gender": "f"}],
  "labels": {"<unit id>": "<expected speaker id or 'narrator'/'ambiguous'>"}
}
Units are produced by `split_units`, so labels key on unit.id.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from castbook.analyze.heuristic import HeuristicAttributor, slugify
from castbook.artifacts import Chapter, Character

GOLD_DIR = Path(__file__).parent / "gold"
REPORT = Path(__file__).parent / "report.md"


def _load(path: Path) -> tuple[Chapter, list[Character], dict[str, str]]:
    raw = json.loads(path.read_text())
    chapter = Chapter(
        index=raw.get("chapter_index", 0),
        title=raw["title"],
        text=raw["text"],
        word_count=len(raw["text"].split()),
    )
    cast = [
        Character(
            id=slugify(c["name"]),
            name=c["name"],
            aliases=c.get("aliases", []),
            gender=c.get("gender", "unknown"),
        )
        for c in raw["cast"]
    ]
    return chapter, cast, raw["labels"]


def evaluate(path: Path) -> dict[str, object]:
    chapter, cast, labels = _load(path)
    units = HeuristicAttributor().attribute(chapter, cast)
    labeled = [u for u in units if u.id in labels]
    correct = sum(1 for u in labeled if u.speaker == labels[u.id])
    missed = [u for u in labeled if u.speaker != labels[u.id]]
    return {
        "name": path.stem,
        "total_units": len(units),
        "labeled": len(labeled),
        "correct": correct,
        "accuracy": correct / len(labeled) if labeled else 0.0,
        "ambiguous": sum(1 for u in units if u.speaker == "ambiguous"),
        "misses": [
            {"unit": u.id, "expected": labels[u.id], "got": u.speaker, "text": u.text[:80]}
            for u in missed
        ],
    }


def main() -> int:
    results = [evaluate(p) for p in sorted(GOLD_DIR.glob("*.json"))]
    lines = [
        "# Castbook attribution eval",
        f"_{datetime.now(timezone.utc).isoformat(timespec='seconds')}Z_",
        "",
        "| book | units | labeled | correct | accuracy | ambiguous |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r['name']} | {r['total_units']} | {r['labeled']} | "
            f"{r['correct']} | {r['accuracy']:.0%} | {r['ambiguous']} |"
        )
    lines += ["", "## Misses", ""]
    for r in results:
        for m in r["misses"]:  # type: ignore[attr-defined]
            miss = m["unit"], m["expected"], m["got"], m["text"]
            lines.append(
                f"- **{r['name']}** `{miss[0]}` expected `{miss[1]}` got `{miss[2]}` — {miss[3]!r}"
            )
    REPORT.write_text("\n".join(lines) + "\n")
    print(REPORT.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
