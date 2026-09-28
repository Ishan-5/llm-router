"""Merge Claude batch replies into one labeled CSV and report the distribution.

Validates every reply file against the batch's expected ticket count before
trusting it, because 238 hand-copied files will eventually contain a
truncated or misnumbered one and a silent positional zip would attach
scores to the wrong tickets.

Outputs:
    labeled_support.csv    query, score, domain, source, batch, serial, ...
    merge_report.txt       per-file status + distribution
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLIES = ROOT / "data" / "claude-replies"
INDEX = ROOT / "data" / "claude-batches" / "row_index.csv"
OUT_CSV = ROOT / "data" / "labeled" / "labeled_support.csv"
OUT_TXT = ROOT / "docs" / "merge_report.txt"

EXPECTED_PER_BATCH = 200
LINE_RE = re.compile(r"^\s*(\d+)\s*[:=]\s*(-?\d+)\s*$")

CHEAP_CEIL = 4.5
FRONTIER_FLOOR = 6.0


def parse_reply(path: Path) -> tuple[dict[int, int], list[str]]:
    """Return (serial -> score, problems)."""
    scores: dict[int, int] = {}
    problems: list[str] = []
    raw_lines = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            # Tolerate prose, but note it.
            if re.search(r"\d", line):
                problems.append(f"unparsed line: {line.strip()[:50]!r}")
            continue
        raw_lines += 1
        serial, score = int(m.group(1)), int(m.group(2))
        if not 0 <= score <= 10:
            problems.append(f"serial {serial}: score {score} out of range")
            continue
        if serial in scores:
            problems.append(f"serial {serial}: duplicate line")
            continue
        scores[serial] = score

    if not scores:
        problems.append("no scores parsed")
        return scores, problems

    expected = set(range(1, len(scores) + 1))
    if set(scores) != expected:
        gaps = sorted(expected ^ set(scores))[:5]
        problems.append(f"serials not 1..{len(scores)} (e.g. {gaps})")
    if len(scores) != EXPECTED_PER_BATCH and not problems:
        problems.append(f"expected {EXPECTED_PER_BATCH} scores, got {len(scores)}")
    return scores, problems


def tier(score: float) -> str:
    if score <= CHEAP_CEIL:
        return "cheap"
    if score >= FRONTIER_FLOOR:
        return "frontier"
    return "mid"


def main() -> int:
    index: dict[tuple[str, int], dict[str, str]] = {}
    with INDEX.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            index[(r["batch"], int(r["serial"]))] = r

    reply_files = sorted(REPLIES.glob("batch_*.txt"))
    out_rows: list[dict[str, str]] = []
    status_lines: list[str] = []
    bad: list[str] = []
    scores_seen = 0
    total_expected = 0

    for path in reply_files:
        batch = path.stem
        meta_rows = [v for k, v in index.items() if k[0] == batch]
        total_expected += len(meta_rows)

        scores, problems = parse_reply(path)
        if problems:
            bad.append(f"{batch}: " + "; ".join(problems[:3]))
            status_lines.append(f"  {batch}  REJECTED  {'; '.join(problems[:2])}")
            continue

        for serial, score in sorted(scores.items()):
            meta = index.get((batch, serial))
            if meta is None:
                bad.append(f"{batch} serial {serial}: no index row")
                continue
            scores_seen += 1
            out_rows.append(
                {
                    "row_id": meta["row_id"],
                    "query": None,  # filled from the batch file below
                    "score": score,
                    "tier": tier(score),
                    "domain": meta["domain"],
                    "source": meta["source"],
                    "source_category": meta["source_category"],
                    "human_priority": meta["human_priority"],
                    "batch": batch,
                    "serial": serial,
                }
            )
        status_lines.append(f"  {batch}  ok  {len(scores)}")

    # Pull query text back out of the batch .md files, positional by serial.
    query_cache: dict[tuple[str, int], str] = {}
    for path in sorted((ROOT / "data" / "claude-batches").glob("batch_*.md")):
        batch = path.stem
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^(\d+)\.\s+(.*)$", line)
            if m:
                query_cache[(batch, int(m.group(1)))] = m.group(2).strip()
    for r in out_rows:
        r["query"] = query_cache.get((r["batch"], int(r["serial"])), "")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "row_id",
        "query",
        "score",
        "tier",
        "domain",
        "source",
        "source_category",
        "human_priority",
        "batch",
        "serial",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out_rows)

    # ---- distribution ----
    dist = Counter(int(r["score"]) for r in out_rows)
    n = len(out_rows)
    lines = [
        f"merge: {len(reply_files)} reply files, {n:,} rows labeled",
        f"expected from index: {total_expected:,}",
        f"rejected files: {len(bad)}",
        "",
        "=== score histogram ===",
    ]
    for k in range(11):
        c = dist.get(k, 0)
        bar = "#" * int(46 * c / n) if n else ""
        lines.append(f"  {k:>2}  {c:>6,}  {100 * c / n:5.1f}%  {bar}")

    lines += ["", "=== bands ==="]
    for name, lo, hi in [("0-2", 0, 2), ("3-5", 3, 5), ("6-8", 6, 8), ("9-10", 9, 10)]:
        c = sum(v for k, v in dist.items() if lo <= k <= hi)
        lines.append(f"  {name:<5} {c:>6,}  {100 * c / n:5.1f}%")

    lines += ["", "=== tier split at 4.5 / 6.0 ==="]
    tcount = Counter(r["tier"] for r in out_rows)
    for t in ("cheap", "mid", "frontier"):
        lines.append(f"  {t:<9} {tcount[t]:>6,}  {100 * tcount[t] / n:5.1f}%")

    lines += ["", "=== by domain ==="]
    for d, c in Counter(r["domain"] for r in out_rows).most_common():
        sub = [int(r["score"]) for r in out_rows if r["domain"] == d]
        fr = sum(1 for x in sub if x >= FRONTIER_FLOOR)
        lines.append(
            f"  {d:<18} {c:>6,}  mean={sum(sub) / len(sub):.2f}  frontier={100 * fr / len(sub):5.1f}%"
        )

    lines += ["", "=== by source ==="]
    for s, c in Counter(r["source"] for r in out_rows).most_common():
        sub = [int(r["score"]) for r in out_rows if r["source"] == s]
        fr = sum(1 for x in sub if x >= FRONTIER_FLOOR)
        lines.append(
            f"  {s:<18} {c:>6,}  mean={sum(sub) / len(sub):.2f}  frontier={100 * fr / len(sub):5.1f}%"
        )

    # Agreement with human priority where we have it (DS3 only).
    pr = [(int(r["score"]), r["human_priority"].strip().lower()) for r in out_rows]
    pr = [(s, p) for s, p in pr if p in ("low", "medium", "high")]
    if pr:
        lines += ["", "=== agreement with human priority (DS3 rows only) ==="]
        lines.append(f"  rows with human priority: {len(pr):,}")
        order = {"low": 0, "medium": 1, "high": 2}
        for label in ("low", "medium", "high"):
            sub = [s for s, p in pr if p == label]
            if sub:
                bar = "#" * int(30 * len(sub) / len(pr))
                lines.append(
                    f"  {label:<7} n={len(sub):>6,}  mean_difficulty={sum(sub) / len(sub):.2f}  {bar}"
                )
        xs = [s for s, _ in pr]
        ys = [order[p] for _, p in pr]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        den = (sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys)) ** 0.5
        lines.append(f"  Spearman-ish correlation: {num / den:.3f}")

    if bad:
        lines += ["", "=== problems ==="] + [f"  {b}" for b in bad[:40]]

    report = "\n".join(lines)
    OUT_TXT.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nwrote {OUT_CSV}  ({n:,} rows)")
    print(f"wrote {OUT_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
