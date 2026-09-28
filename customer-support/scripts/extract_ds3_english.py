"""Extract the English-only subset of the Tobi-Bueck ticket datasets (DS3).

The family ships four CSV variants; two of them are German-only and two
are multilingual. Filtering to language == 'en' matters a lot here: the
raw files are majority German, and training on them unfiltered produces
a support model that answers in German.

The variants overlap - the 20k and 28.5k files share 4,514 English rows -
so dedup is on (subject, body) lowercased, keeping the first occurrence.

Outputs raw-datasets/customer-support-dataset-3/english_tickets.csv with
the columns needed for difficulty labelling plus the human labels that
came with the data (queue / priority / type), which are useful later as a
sanity check on Claude's scores.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS3 = ROOT / "raw-datasets" / "customer-support-dataset-3"
OUT_CSV = DS3 / "english_tickets.csv"

# Ordered so smaller files win the dedup; keeps the earliest variant's row.
SOURCES = [
    "dataset-tickets-multi-lang3-4k.csv",
    "dataset-tickets-multi-lang-4-20k.csv",
    "aa_dataset-tickets-multi-lang-5-2-50-version.csv",
]

# Deliberately excluded: these two are 100% German (0 English rows).
SKIPPED = [
    "dataset-tickets-german_normalized.csv",
    "dataset-tickets-german_normalized_50_5_2.csv",
]

MIN_WORDS = 5  # below this there is nothing to score
OUT_COLS = [
    "query",
    "subject",
    "queue",
    "priority",
    "type",
    "business_type",
    "has_agent_answer",
    "source_file",
]


def key_for(row: dict[str, str]) -> str:
    subject = (row.get("subject") or "").strip().lower()
    body = (row.get("body") or "").strip().lower()
    return hashlib.md5(f"{subject}||{body}".encode("utf-8")).hexdigest()


def main() -> int:
    seen: set[str] = set()
    kept: list[dict[str, str]] = []
    stats: Counter[str] = Counter()

    for name in SOURCES:
        path = DS3 / name
        if not path.exists():
            print(f"  MISSING {name}")
            continue

        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                stats[f"{name}:total"] += 1

                if (row.get("language") or "").strip().lower() != "en":
                    stats[f"{name}:non_english"] += 1
                    continue
                stats[f"{name}:english"] += 1

                body = (row.get("body") or "").strip()
                if len(body.split()) < MIN_WORDS:
                    stats[f"{name}:too_short"] += 1
                    continue

                k = key_for(row)
                if k in seen:
                    stats[f"{name}:duplicate"] += 1
                    continue
                seen.add(k)

                subject = (row.get("subject") or "").strip()
                query = f"{subject}\n\n{body}".strip() if subject else body
                kept.append(
                    {
                        "query": query,
                        "subject": subject,
                        "queue": (row.get("queue") or "").strip(),
                        "priority": (row.get("priority") or "").strip(),
                        "type": (row.get("type") or "").strip(),
                        "business_type": (row.get("business_type") or "").strip(),
                        "has_agent_answer": "1" if (row.get("answer") or "").strip() else "0",
                        "source_file": name,
                    }
                )

    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(kept)

    print("per-file filtering")
    for name in SOURCES:
        t = stats[f"{name}:total"]
        if not t:
            continue
        en, dup, short = (
            stats[f"{name}:english"],
            stats[f"{name}:duplicate"],
            stats[f"{name}:too_short"],
        )
        print(f"  {name[:46]:<46} total={t:<6} en={en:<6} dup={dup:<5} short={short}")
    for name in SKIPPED:
        print(f"  SKIPPED (German-only): {name}")

    print(f"\nwrote {OUT_CSV}")
    print(f"  rows kept: {len(kept):,}")

    q = Counter(r["queue"] for r in kept)
    print("\nqueue distribution")
    for k, v in q.most_common():
        print(f"  {k[:34]:<34} {v:<6} {100 * v / len(kept):5.1f}%")

    p = Counter(r["priority"] for r in kept)
    print("priority distribution")
    for k, v in p.most_common():
        print(f"  {k[:34]:<34} {v:<6} {100 * v / len(kept):5.1f}%")

    words = sorted(len(r["query"].split()) for r in kept)
    print(
        f"\nquery length: min={words[0]} p50={words[len(words) // 2]} "
        f"p90={words[len(words) * 9 // 10]} max={words[-1]}"
    )
    print(f"  with agent answer: {sum(1 for r in kept if r['has_agent_answer'] == '1'):,}")
    print("\nsample queries")
    for r in kept[:3]:
        print(f"  [{r['queue']}] {r['query'][:100]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
