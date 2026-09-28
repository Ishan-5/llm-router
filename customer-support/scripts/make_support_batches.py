"""Build Claude labeling batches for the customer-support difficulty labels.

Mirrors the pipeline used for the general 8,200 labels at
D:\\llm-router-ml-upgrade\\final: a .md file per batch containing the rubric
and numbered queries, and a matching .txt reply file that Claude fills with
"N: <score>" lines. Serial numbers are positional, so merging is a straight
zip - the same contract the old pipeline used.

Differences from the old run, all deliberate:
  - 200 queries per batch instead of 100 (50,063 rows is 7.5x the old set)
  - the support-specific rubric, including the two anti-patterns Claude
    flagged: emotional tone is not difficulty, and missing data is not
    difficulty
  - domain + source are emitted as a trailing comment block so a mismatched
    reply can be spotted by eye, and so provenance survives into the merge

Usage:
    python make_support_batches.py                 # all batches
    python make_support_batches.py --limit 3       # first 3, for the histogram check
    python make_support_batches.py --shuffle-seed 7
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ROOT / "data" / "domain-splits"
OUT = ROOT / "data" / "claude-batches"

BATCH_SIZE = 200
# Truncation for the prompt. Median support ticket is 62 words, p90 is 101,
# so 900 chars covers the vast majority without bloating the prompt.
MAX_QUERY_CHARS = 900

RUBRIC = """You are scoring customer support tickets for an LLM cost-routing system. Each ticket below was sent to an AI model, and we need to know how hard it is to answer WELL. Easy tickets will be routed to a cheap model, hard ones to an expensive one. Score every ticket from 0 to 10.

Score the effort required to identify and deliver the CORRECT resolution action - not the tone, length, urgency, or emotional intensity of the request, and not the real-world severity of the customer's problem.

0-2 = Trivial: single unambiguous action or fact, all needed info present, no diagnosis or judgment required. Greetings, hours/policy lookups with one clear answer, "cancel order #X", "what is your return window".
3-5 = Moderate: a short known troubleshooting sequence with a known fix path, combining 2-3 stated facts into an answer, one clarifying question before resolution, or a standard calculation/explanation (proration, standard refund timeline). The customer's emotional state can be intense here without moving the score.
6-8 = Hard: real differential diagnosis across multiple plausible causes with no obvious single fix; a policy that has exceptions or interacts with another policy; technical troubleshooting that requires reasoning about system internals rather than "try these 3 steps"; or a multi-part ticket where the parts have different resolution paths and none can be dropped.
9-10 = Expert: rules that conflict and require judgment to resolve (e.g. two jurisdictions' legal requirements pointing opposite directions), or novel technical failures with no known pattern that require hypothesis generation across multiple system layers.

CRITICAL RULES:
- Angry, urgent, or emotional tone does NOT raise the score unless it changes what the correct written response must contain.
- If the correct response is "ask a clarifying question" or "request data you don't have access to", score LOW (1-3) even if the underlying problem sounds serious. Recognising and requesting missing information is a low-effort, well-defined action.
- Do NOT score on LENGTH. A long angry email about a simple refund is still a 1-2. A short but genuinely multi-step technical question can be hard.
- For multi-part tickets, score near the hardest individual part, not the sum of all parts.
- Judge each ticket independently. Use the full 0-10 range if the range is warranted; do not compress toward the middle.

Reply with ONLY the scores, one per ticket, in this exact format:
1: <score>
2: <score>
...but nothing else. No explanation, no commentary, no restating the rubric.

Tickets:"""

BUCKETS = ["account_access", "orders_billing", "technical", "delivery_general"]


def load_all() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for name in BUCKETS:
        path = SPLITS / f"{name}.csv"
        if not path.exists():
            print(f"  MISSING {path}")
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for i, r in enumerate(csv.DictReader(fh)):
                q = (r.get("query") or "").strip()
                if len(q.split()) < 3:
                    continue
                rows.append(
                    {
                        "row_id": f"{name}_{i:06d}",
                        "query": q,
                        "domain": r.get("domain", name),
                        "source": r.get("source", ""),
                        "source_category": r.get("source_category", ""),
                        "source_intent": r.get("source_intent", ""),
                        "human_priority": r.get("human_priority", ""),
                        "human_queue": r.get("human_queue", ""),
                    }
                )
    return rows


def dedupe(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    """Drop near-identical tickets on an exact-normalised query match.

    DS2 is synthetic and repeats templates, and Bitext variants differ only
    by register tags in many cases, so exact-normalised dedup recovers a
    meaningful number of rows without needing embeddings.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    seen: set[str] = set()
    out: list[dict[str, str]] = []
    dropped = 0
    for r in rows:
        k = norm(r["query"])
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        out.append(r)
    return out, dropped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    ap.add_argument("--limit", type=int, default=0, help="only write the first N batches")
    ap.add_argument("--shuffle-seed", type=int, default=42)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_all()
    total_raw = len(rows)
    rows, dropped = dedupe(rows)
    print(f"  loaded        : {total_raw:,}")
    print(f"  after dedupe  : {len(rows):,}  (dropped {dropped:,})")

    domains = Counter(r["domain"] for r in rows)
    print("  per domain    :")
    for d, n in domains.most_common():
        print(f"      {d:<18} {n:>7,}  {100 * n / len(rows):5.1f}%")
    print("  per source    :")
    for s, n in Counter(r["source"] for r in rows).most_common():
        print(f"      {s:<18} {n:>7,}")

    # Shuffle so every batch is a domain mix. Batches must not be sorted by
    # domain or the labeler sees a monotone run and drifts.
    rng = random.Random(args.shuffle_seed)
    rng.shuffle(rows)

    batches = [rows[i : i + args.batch_size] for i in range(0, len(rows), args.batch_size)]
    if args.limit:
        batches = batches[: args.limit]

    # row_id index for the merge step
    index_path = out_dir / "row_index.csv"
    with index_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row_id", "batch", "serial", "domain", "source", "source_category", "human_priority"])
        for bi, batch in enumerate(batches, 1):
            for si, r in enumerate(batch, 1):
                w.writerow(
                    [
                        r["row_id"],
                        f"batch_{bi:03d}",
                        si,
                        r["domain"],
                        r["source"],
                        r["source_category"],
                        r["human_priority"],
                    ]
                )

    for bi, batch in enumerate(batches, 1):
        lines = [RUBRIC, ""]
        for si, r in enumerate(batch, 1):
            q = r["query"].replace("\n", " ").replace("\r", " ")
            if len(q) > MAX_QUERY_CHARS:
                q = q[: MAX_QUERY_CHARS - 3] + "..."
            lines.append(f"{si}. {q}")
        lines.append("")
        lines.append("---")
        lines.append("Batch reference (for your own sanity check, do not score on it):")
        bd = Counter(r["domain"] for r in batch)
        bs = Counter(r["source"] for r in batch)
        lines.append("  domains: " + ", ".join(f"{k}={v}" for k, v in sorted(bd.items())))
        lines.append("  sources: " + ", ".join(f"{k}={v}" for k, v in sorted(bs.items())))
        lines.append(f"  total tickets: {len(batch)}")
        lines.append(f"  reply with exactly {len(batch)} lines, numbered 1 to {len(batch)}.")

        (out_dir / f"batch_{bi:03d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nwrote {len(batches)} batches to {out_dir}")
    print(f"  {args.batch_size} tickets each, reply file expected: batch_NNN.txt")
    print(f"  row index: {index_path.name} ({len(rows):,} rows)")
    if args.limit:
        print(f"\n  LIMIT MODE: only {len(batches)} batches written (histogram check first)")

    est_words = sum(len(r["query"].split()) for b in batches for r in b)
    print(f"  approx prompt words across all batches: {est_words:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
