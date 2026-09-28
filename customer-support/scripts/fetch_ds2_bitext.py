"""Download the Bitext customer-support dataset into customer-support/raw-datasets.

Source: bitext/Bitext-customer-support-llm-chatbot-training-dataset
27 intents / 10 categories, 26,872 instruction-response pairs, synthetic.

We fetch the CSV directly rather than via load_dataset() because the
dataset ships as a single CSV and we only need the instruction text for
difficulty labelling. Prints the shape so the row count can be checked
against the description (26,872) before anyone spends API calls on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "bitext/Bitext-customer-support-llm-chatbot-training-dataset"
FILENAME = "Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv"

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "raw-datasets" / "customer-support-dataset-2"
OUT_CSV = OUT_DIR / "bitext_customer_support_27k.csv"

EXPECTED_ROWS = 26_872


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"fetching {FILENAME} from {REPO}")
    try:
        cached = hf_hub_download(
            repo_id=REPO,
            filename=FILENAME,
            repo_type="dataset",
        )
    except Exception as exc:  # noqa: BLE001 - surface the real cause
        print(f"\nDOWNLOAD FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "\nThis is a network or auth issue, not a code bug. Check:\n"
            "  - outbound HTTPS to huggingface.co is allowed\n"
            "  - if you are behind a proxy, set HTTPS_PROXY before running\n"
            "  - HF_TOKEN is set if the repo rate-limits anonymous access",
            file=sys.stderr,
        )
        return 1

    import shutil

    shutil.copyfile(cached, OUT_CSV)

    import csv

    with OUT_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    print(f"\nwrote {OUT_CSV}")
    print(f"  rows   : {len(rows):,}")
    print(f"  columns: {', '.join(fieldnames)}")

    if EXPECTED_ROWS and len(rows) != EXPECTED_ROWS:
        print(
            f"  NOTE: expected {EXPECTED_ROWS:,} rows, got {len(rows):,}. "
            "Fine if upstream changed; just re-check before labelling."
        )

    # The instruction column is the customer utterance we will label.
    for candidate in ("instruction", "query", "question"):
        if candidate in fieldnames:
            texts = [(r.get(candidate) or "").strip() for r in rows]
            nonempty = [t for t in texts if t]
            uniq = len(set(nonempty))
            print(f"\n  '{candidate}':")
            print(f"    nonempty : {len(nonempty):,}")
            print(f"    unique   : {uniq:,}")
            if nonempty:
                dup_rate = 100 * (1 - uniq / max(1, len(nonempty)))
                print(f"    dup rate : {dup_rate:.1f}%")
                for text in nonempty[:3]:
                    print(f"    e.g. {text[:88]!r}")
            break
    else:
        print("\n  WARNING: no instruction-like column found; inspect headers above.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
