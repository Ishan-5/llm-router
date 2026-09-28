"""Build the final support training set: query, score, domain.

Three columns, nothing else. Source is the merged labeled_support.csv
(17,600 rows).

  domain is the raw key: technical, orders_billing, delivery_general,
  account_access. The counts are uneven, so a `domain` column is worth
  keeping if you ever train per-domain models or inspect errors by category.

Outputs:
    data/final/train_final.csv
    data/final/train_final_summary.txt
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "labeled" / "labeled_support.csv"
OUT_DIR = ROOT / "data" / "final"
OUT_CSV = OUT_DIR / "train_final.csv"
OUT_TXT = OUT_DIR / "train_final_summary.txt"


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"missing {SRC}; run merge_support_labels.py first")

    rows = [
        r
        for r in csv.DictReader(SRC.open(encoding="utf-8"))
        if r["query"].strip() and r["score"].strip()
    ]

    out = []
    for r in rows:
        score = int(float(r["score"]))
        if not 0 <= score <= 10:
            raise SystemExit(f"{r['row_id']}: score {score} out of range")
        out.append(
            {
                "query": r["query"].strip(),
                "score": score,
                "domain": r["domain"],
            }
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["query", "score", "domain"])
        w.writeheader()
        w.writerows(out)

    n = len(out)
    lines = [f"final support training set: {n:,} rows", "", "=== domain ==="]
    for dom, c in Counter(r["domain"] for r in out).most_common():
        sub = [r["score"] for r in out if r["domain"] == dom]
        lines.append(
            f"  {dom:<18} {c:>6,}  {100 * c / n:5.1f}%  mean score {sum(sub) / len(sub):.2f}"
        )

    lines += ["", "=== score ==="]
    dist = Counter(r["score"] for r in out)
    for k in range(11):
        c = dist.get(k, 0)
        bar = "#" * int(46 * c / n) if n else ""
        lines.append(f"  {k:>2}  {c:>6,}  {100 * c / n:5.1f}%  {bar}")
    lines.append(f"  mean {sum(r['score'] for r in out) / n:.2f}")

    lines += [
        "",
        "=== integrity ===",
        f"  duplicate query strings: {n - len({r['query'] for r in out})}",
        f"  empty queries: {sum(1 for r in out if not r['query'].strip())}",
    ]

    OUT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {OUT_CSV}  ({n:,} rows, 3 columns: query, score, domain)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
