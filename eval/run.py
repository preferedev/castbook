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

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from castbook.analyze.attributor import Attributor
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


def evaluate(path: Path, attributor: Attributor) -> dict[str, object]:
    chapter, cast, labels = _load(path)
    units = attributor.attribute(chapter, cast)
    labeled = [u for u in units if u.id in labels]
    from castbook.analyze.reconcile import normalize

    def same(a: str, b: str) -> bool:
        a, b = normalize(a), normalize(b)
        return a == b or a.endswith(f" {b}") or b.endswith(f" {a}")

    correct = sum(1 for u in labeled if same(u.speaker, labels[u.id]))
    missed = [u for u in labeled if not same(u.speaker, labels[u.id])]
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use Qwen3-4B instead of heuristic")
    ap.add_argument(
        "--hybrid", action="store_true", help="heuristic + LLM second opinion on unsure units"
    )
    ap.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="exit 1 if any book scores below this accuracy (0-1)",
    )
    args = ap.parse_args()
    attributor: Attributor = HeuristicAttributor()
    if args.llm or args.hybrid:
        from castbook.analyze.llm import LlamaCppAttributor
        from castbook.config import Settings
        from castbook.models import resolve_model

        cfg = Settings.load()
        path = resolve_model(cfg.models_dir, cfg.llm.model)
        if path is None:
            raise SystemExit(f"model not downloaded: castbook models pull {cfg.llm.model}")
        llm = LlamaCppAttributor(path, cfg.llm)
        if args.hybrid:
            from castbook.analyze.hybrid import HybridAttributor

            attributor = HybridAttributor(HeuristicAttributor(), llm)
        else:
            attributor = llm

    results = [evaluate(p, attributor) for p in sorted(GOLD_DIR.glob("*.json"))]
    lines = [
        "# Castbook attribution eval",
        f"_{datetime.now(timezone.utc).isoformat(timespec='seconds')}Z — {attributor.name}_",
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
    if args.fail_under is not None:
        below = [r["name"] for r in results if r["accuracy"] < args.fail_under]
        if below:
            print(f"FAIL: below {args.fail_under:.0%}: {', '.join(below)}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
