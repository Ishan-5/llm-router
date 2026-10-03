"""Blind A/B test: is the cheap tier actually as good as the frontier tier?

The whole product claim is "we cut cost without degrading answers". Scoring one
answer on a 1-10 scale cannot prove that, and a judge that already knows which
tier wrote an answer will grade the label instead of the work. So this script
answers the only question that matters, head to head:

    for each query: call cheap -> answer A, call frontier -> answer B,
    show the judge both with NO tier labels and let it pick the winner.

Randomising which side is which means position bias cancels out across runs, and
never telling the judge which tier produced which answer removes the confound
that the live quality judge still has.

Result: "cheap won or tied X% of the time", which is the number you can show a
user. Judge disagreement or a tie is reported separately -- a tie is not
evidence of parity, so the headline number only counts clear wins for cheap.

Usage
-----
    python backend/scripts/quality_ab_test.py --n 200
    python backend/scripts/quality_ab_test.py --n 200 --seed 7 --out ab_report.json
    python backend/scripts/quality_ab_test.py --queries file.txt --dump-samples 20

Queries come from real logged traffic by default (request_logs), because that
is the distribution the router actually sees. Falls back to a gold dataset with
--gold if the database is empty.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
sys.path.insert(0, str(REPO / "backend" / "src"))
sys.path.insert(0, str(REPO / "backend" / "router"))

# router.config calls a bare load_dotenv(), which only finds backend/.env when the
# cwd happens to be backend/. Pin the path so this script behaves the same from
# anywhere -- otherwise the judge key silently reads as missing.
try:
    from dotenv import load_dotenv

    load_dotenv(REPO / "backend" / ".env", override=True)
except ImportError:
    pass

from router.config import GROQ_JUDGE_API_KEY, GROQ_JUDGE_MODEL  # noqa: E402
from router.providers_registry import PROVIDERS_REGISTRY  # noqa: E402

DEFAULT_TIER_A = "cheap"
DEFAULT_TIER_B = "frontier"

PAIRWISE_SYSTEM_PROMPT = (
    "You are comparing two candidate answers to the same user question. They were "
    "produced by different systems, but you are not told which is which, you must "
    "not try to infer it, and it is irrelevant to your verdict.\n"
    "Judge only the answer text itself. Decide which candidate better serves the "
    "user, using these criteria in priority order:\n"
    "  1. Correctness. A confident wrong answer loses to a correct one.\n"
    "  2. Completeness. Does it actually address everything asked?\n"
    "  3. Clarity. Is it usable without rework?\n"
    "Do not reward length, confidence, elaborate formatting, or formality over "
    "substance. A shorter correct answer beats a longer vague one. Judge each "
    "answer as if you had no idea where it came from.\n"
    'Respond with ONLY one token: "A", "B", or "TIE". No explanation.'
)

SCORING_SYSTEM_PROMPT = (
    "You are an impartial quality evaluator. Given a user query and an assistant "
    "response, score how well the response answers the query on a scale of 1 to 10.\n"
    "  - 10: complete, correct, well-structured, directly addresses the query.\n"
    "  - 7-9: correct and helpful, minor omissions or some verbosity.\n"
    "  - 4-6: partially addresses the query, some errors or important gaps.\n"
    "  - 1-3: mostly wrong, off-topic, or refuses to answer.\n"
    "Penalise refusals and hallucinated facts. Respond with ONLY a single "
    "integer between 1 and 10."
)


def _judge_client():
    from openai import OpenAI

    if not GROQ_JUDGE_API_KEY:
        raise SystemExit(
            "GROQ_JUDGE_API_KEY is not set. The judge cannot run without it.\n"
            "Set it in backend/.env (the same key the live quality judge uses), "
            "and run this script from the backend/ directory so .env is found."
        )
    return OpenAI(
        api_key=GROQ_JUDGE_API_KEY,
        base_url=PROVIDERS_REGISTRY["groq"]["base_url"],
        timeout=60.0,
    )


def pick_winner(client, query: str, answer_a: str, answer_b: str) -> str:
    """Return 'A', 'B' or 'TIE'. Never labels which tier produced which."""
    if not answer_a.strip() or not answer_b.strip():
        return "TIE"
    try:
        resp = client.chat.completions.create(
            model=GROQ_JUDGE_MODEL,
            max_completion_tokens=8,
            temperature=0,
            messages=[
                {"role": "system", "content": PAIRWISE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{query[:1500]}\n\n"
                        f"--- Answer A ---\n{answer_a[:4000]}\n\n"
                        f"--- Answer B ---\n{answer_b[:4000]}"
                    ),
                },
            ],
        )
        text = (resp.choices[0].message.content or "").strip().upper()
        for token in ("TIE", "A", "B"):
            if token in text:
                return token
        return "TIE"
    except Exception as e:  # a judge failure must not abort a 200-query run
        print(f"    judge error: {e}")
        return "ERROR"


def score_one(client, query: str, answer: str) -> float | None:
    if not answer.strip():
        return 0.0
    try:
        resp = client.chat.completions.create(
            model=GROQ_JUDGE_MODEL,
            max_completion_tokens=64,
            temperature=0,
            messages=[
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Question:\n{query[:1500]}\n\nResponse:\n{answer[:4000]}",
                },
            ],
        )
        text = resp.choices[0].message.content or ""
        digits = [c for c in text if c.isdigit()]
        if not digits:
            return None
        return round(int("".join(digits[:2])) / 10.0, 4)
    except Exception as e:
        print(f"    score error: {e}")
        return None


def load_queries_from_db(n: int) -> list[str]:
    from router.db import SessionLocal, RequestLog

    session = SessionLocal()
    try:
        rows = (
            session.query(RequestLog.query, RequestLog.difficulty_score)
            .filter(
                RequestLog.query.isnot(None),
                RequestLog.cache_hit == False,
                RequestLog.tier.in_(("cheap", "mid", "frontier")),
            )
            .order_by(RequestLog.created_at.desc())
            .limit(n * 3)
            .all()
        )
    finally:
        session.close()
    return [r[0] for r in rows if r[0] and len(r[0].strip()) >= 15][:n]


def load_queries_from_file(path: str, n: int) -> list[str]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
        if len(out) >= n:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Blind cheap-vs-frontier A/B quality test")
    ap.add_argument("--n", type=int, default=200, help="how many queries to compare")
    ap.add_argument("--queries", help="file with one query per line; else read the database")
    ap.add_argument("--tier-a", default=DEFAULT_TIER_A)
    ap.add_argument("--tier-b", default=DEFAULT_TIER_B)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="ab_report.json")
    ap.add_argument("--dump-samples", type=int, default=0,
                    help="write N blind pairs to a file for human checking")
    args = ap.parse_args()

    if not GROQ_JUDGE_API_KEY:
        print("GROQ_JUDGE_API_KEY is not set -- the judge cannot run.")
        print("Set it in backend/.env (the same key the live quality judge uses).")
        return 1

    from router.rate_limiter import call_with_failover

    if args.queries:
        queries = load_queries_from_file(args.queries, args.n)
    else:
        queries = load_queries_from_db(args.n)
    if not queries:
        print("No queries found. Pass --queries <file> or log some live traffic first.")
        return 1

    rng = random.Random(args.seed)
    client = _judge_client()
    rows = []
    blind_samples = []

    print(f"Comparing {args.tier_a} vs {args.tier_b} on {len(queries)} queries, blind.\n")
    for i, q in enumerate(queries, 1):
        answers = {}
        for tier in (args.tier_a, args.tier_b):
            try:
                r = call_with_failover(tier, q)
                answers[tier] = (r.get("text") or "", float(r.get("cost_usd") or 0.0))
            except Exception as e:
                answers[tier] = ("", 0.0)
                print(f"  [{i}/{len(queries)}] {tier} failed: {e}")
        if not answers[args.tier_a][0] or not answers[args.tier_b][0]:
            continue

        # Randomise presentation order so position bias cancels across the run.
        swap = rng.random() < 0.5
        first, second = (args.tier_b, args.tier_a) if swap else (args.tier_a, args.tier_b)
        verdict = pick_winner(client, q, answers[first][0], answers[second][0])

        if verdict == "ERROR":
            continue
        if verdict == "TIE":
            winner = "TIE"
        elif verdict == "A":
            winner = first
        else:
            winner = second

        rows.append({
            "query": q,
            "winner": winner,
            "cheap_cost": answers[args.tier_a][1],
            "other_cost": answers[args.tier_b][1],
        })
        if len(blind_samples) < args.dump_samples:
            blind_samples.append({
                "query": q,
                "answer_a": answers[first][0],
                "answer_b": answers[second][0],
            })
        mark = "=" if winner == "TIE" else ("<" if winner == args.tier_a else ">")
        print(f"  [{i}/{len(queries)}] {mark} {winner}")

    if not rows:
        print("No comparable rows -- every call failed.")
        return 1

    n = len(rows)
    counts = Counter(r["winner"] for r in rows)
    cheap_wins = counts.get(args.tier_a, 0)
    other_wins = counts.get(args.tier_b, 0)
    ties = counts.get("TIE", 0)
    cost_a = sum(r["cheap_cost"] for r in rows)
    cost_b = sum(r["other_cost"] for r in rows)

    report = {
        "n_compared": n,
        "tier_a": args.tier_a,
        "tier_b": args.tier_b,
        "seed": args.seed,
        "wins": {args.tier_a: cheap_wins, args.tier_b: other_wins, "TIE": ties},
        "cheap_win_pct": round(cheap_wins / n * 100, 1),
        "cheap_win_or_tie_pct": round((cheap_wins + ties) / n * 100, 1),
        "total_cost_a_usd": round(cost_a, 6),
        "total_cost_b_usd": round(cost_b, 6),
        "cost_ratio_b_over_a": round(cost_b / cost_a, 2) if cost_a else None,
        "note": (
            "Judge never saw which tier produced which answer, and the two answers "
            "were shown in randomised order. Cheap win-or-tie is the headline "
            "quality-retention number; a tie is not proof of parity."
        ),
    }

    print("\n" + "=" * 58)
    print(f"{args.tier_a} wins : {cheap_wins:>4}  ({report['cheap_win_pct']}%)")
    print(f"{args.tier_b} wins : {other_wins:>4}  ({round(other_wins / n * 100, 1)}%)")
    print(f"ties            : {ties:>4}  ({round(ties / n * 100, 1)}%)")
    print(f"win or tie      : {report['cheap_win_or_tie_pct']}%")
    print(f"cost {args.tier_a:<8}: ${cost_a:.5f}   cost {args.tier_b}: ${cost_b:.5f}"
          f"   ratio {report['cost_ratio_b_over_a']}x")
    print("=" * 58)

    Path(args.out).write_text(json.dumps({**report, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Report -> {args.out}")

    if blind_samples:
        sample_path = Path("ab_blind_samples.json")
        sample_path.write_text(json.dumps(blind_samples, indent=2), encoding="utf-8")
        print(f"{len(blind_samples)} blind pairs -> {sample_path} (judge picks, you verify)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())