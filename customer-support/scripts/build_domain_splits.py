"""Cross-walk DS2 and DS3 taxonomies into 4 support domain buckets.

DS2 and DS3 use different taxonomies and, more importantly, describe
different businesses:

  DS2 (Bitext, synthetic)  commerce / e-commerce transactional support
  DS3 (Tobi-Bueck, real)   IT helpdesk

So this is not a 1:1 join. Some DS3 queues have no DS2 counterpart
(Technical Support, IT Support, Service Outages) and some DS2 categories
have no DS3 counterpart (DELIVERY, SHIPPING, SUBSCRIPTION). Buckets are
therefore built by explicit mapping, and the script reports what is left
over so nothing disappears silently.

Output: one CSV per bucket, plus a summary. No labelling here - these are
the inputs the Claude labelling pass will consume.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DS2 = ROOT / "raw-datasets" / "customer-support-dataset-2" / "bitext_customer_support_27k.csv"
DS3 = ROOT / "raw-datasets" / "customer-support-dataset-3" / "english_tickets.csv"
OUT = ROOT / "data" / "domain-splits"

# Bucket name -> DS2 categories
DS2_MAP = {
    "account_access": ["ACCOUNT", "SUBSCRIPTION"],
    "orders_billing": ["ORDER", "REFUND", "INVOICE", "PAYMENT", "CANCEL"],
    "technical": [],  # no DS2 counterpart
    "delivery_general": ["DELIVERY", "SHIPPING", "CONTACT", "FEEDBACK"],
}

# Bucket name -> DS3 queues
DS3_MAP = {
    "account_access": [],
    "orders_billing": ["Billing and Payments", "Returns and Exchanges"],
    "technical": [
        "Technical Support",
        "Product Support",
        "IT Support",
        "Service Outages and Maintenance",
    ],
    "delivery_general": [
        "Customer Service",
        "Sales and Pre-Sales",
        "Human Resources",
        "General Inquiry",
    ],
}

MIN_WORDS = 5
PLACEHOLDERS = {
    "{{Order Number}}": "8472910",
    "{{Invoice Number}}": "INV-20418",
    "{{Online Order Interaction}}": "my account order page",
    "{{Online Payment Interaction}}": "the checkout payment screen",
    "{{Online Navigation Step}}": "the orders page",
    "{{Online Customer Support Channel}}": "the support chat widget",
    "{{Profile}}": "my profile",
    "{{Profile Type}}": "personal",
    "{{Settings}}": "account settings",
    "{{Online Company Portal Info}}": "the help portal",
    "{{Date}}": "March 14",
    "{{Date Range}}": "March 1 to March 14",
    "{{Shipping Cut-off Time}}": "2pm",
    "{{Delivery City}}": "Austin",
    "{{Delivery Country}}": "United States",
    "{{Salutation}}": "Hi",
    "{{Client First Name}}": "Jordan",
    "{{Client Last Name}}": "Reyes",
    "{{Customer Support Phone Number}}": "1-800-555-0142",
    "{{Customer Support Email}}": "support@example.com",
    "{{Live Chat Support}}": "live chat",
    "{{Website URL}}": "example.com",
    "{{Upgrade Account}}": "premium",
    "{{Account Type}}": "business",
    "{{Account Category}}": "standard",
    "{{Account Change}}": "switch account",
    "{{Program}}": "loyalty",
    "{{Refund Amount}}": "49.99",
    "{{Money Amount}}": "120.50",
    "{{Store Location}}": "the downtown store",
}


def fill(text: str) -> str:
    for token, value in PLACEHOLDERS.items():
        text = text.replace(token, value)
    return " ".join(text.split())


def load_ds2() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    unmapped: Counter[str] = Counter()
    with DS2.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            cat = (row.get("category") or "").strip()
            bucket = next((b for b, cats in DS2_MAP.items() if cat in cats), None)
            if bucket is None:
                unmapped[cat] += 1
                continue
            q = fill((row.get("instruction") or "").strip())
            if len(q.split()) < MIN_WORDS:
                continue
            out[bucket].append(
                {
                    "query": q,
                    "domain": bucket,
                    "source": "ds2_bitext",
                    "source_category": cat,
                    "source_intent": (row.get("intent") or "").strip(),
                    "human_priority": "",
                    "human_queue": "",
                }
            )
    if unmapped:
        print("  DS2 categories left unmapped:")
        for k, v in unmapped.most_common():
            print(f"    {k:<24} {v}")
    return out


def load_ds3() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    unmapped: Counter[str] = Counter()
    with DS3.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            q = (row.get("query") or "").strip()
            if len(q.split()) < MIN_WORDS:
                continue
            queue = (row.get("queue") or "").strip()
            bucket = next((b for b, qs in DS3_MAP.items() if queue in qs), None)
            if bucket is None:
                unmapped[queue] += 1
                continue
            out[bucket].append(
                {
                    "query": q,
                    "domain": bucket,
                    "source": "ds3_tobi_bueck",
                    "source_category": queue,
                    "source_intent": "",
                    "human_priority": (row.get("priority") or "").strip(),
                    "human_queue": queue,
                }
            )
    if unmapped:
        print("  DS3 queues left unmapped:")
        for k, v in unmapped.most_common():
            print(f"    {k:<34} {v}")
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cols = [
        "query",
        "domain",
        "source",
        "source_category",
        "source_intent",
        "human_priority",
        "human_queue",
    ]

    print("mapping")
    a, b = load_ds2(), load_ds3()

    total = 0
    summary = []
    for bucket in DS2_MAP:
        rows = a.get(bucket, []) + b.get(bucket, [])
        total += len(rows)
        path = OUT / f"{bucket}.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

        n2 = len(a.get(bucket, []))
        n3 = len(b.get(bucket, []))
        prov = "DS3 only" if n2 == 0 else ("DS2 only" if n3 == 0 else "mixed")
        summary.append((bucket, len(rows), n2, n3, prov, path.name))
        print(f"\nwrote {path.name}  ({len(rows):,} rows, {prov})")
        for k, v in Counter(r["source_category"] for r in rows).most_common(6):
            print(f"    {k[:40]:<40} {v:>6}")

    print("\n" + "=" * 68)
    print(f"{'bucket':<18}{'rows':>8}{'ds2':>8}{'ds3':>8}   provenance")
    print("-" * 68)
    for bucket, n, n2, n3, prov, _ in summary:
        print(f"{bucket:<18}{n:>8,}{n2:>8,}{n3:>8,}   {prov}")
    print("-" * 68)
    print(f"{'TOTAL':<18}{total:>8,}")

    src_total = sum(1 for _ in DS2.open(encoding="utf-8")) + sum(1 for _ in DS3.open(encoding="utf-8")) - 2
    print(f"\ninput rows: {src_total:,}   output rows: {total:,}   delta: {src_total - total:,}")

    print("\nper bucket")
    for bucket, n, _, _, _, _ in summary:
        share = 100 * n / total if total else 0
        bar = "#" * int(30 * n / total) if total else ""
        print(f"  {bucket:<18} {n:>6,}  {share:5.1f}%  {bar}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
