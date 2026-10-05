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
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# A graded pair has to have real content on both sides. Anything shorter than this
# is a truncated or refused generation, and grading it produces noise.
MIN_ANSWER_CHARS = 40

# gpt-oss-120b is a reasoning model: it spends ~130-190 completion tokens
# reasoning before emitting the verdict. Measured, not guessed.
JUDGE_MAX_TOKENS = 1024

# Groq bills gpt-oss-120b against a 200k token/day cap that the LIVE quality
# judge shares. Long answer excerpts blew through it, so cap how much text the
# pairwise judge reads. 1200 chars is roughly a screenful -- past that the
# verdict does not change.
JUDGE_ANSWER_CHARS = 1200
JUDGE_RETRIES = 4


class BlankAnswer(RuntimeError):
    """Raised when a pair cannot be graded. Never silently becomes a TIE."""

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
    "Use TIE whenever both answers would reasonably be accepted by the user. If "
    "one answer is merely more detailed but no more correct or more useful, that "
    "is a TIE, not a win. Do not pick a winner merely to avoid returning TIE.\n"
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
        raise BlankAnswer(
            "refusing to grade a pair with a blank answer -- an empty pair is "
            "not a tie, it is a missing measurement"
        )
    last_err = None
    for attempt in range(JUDGE_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=GROQ_JUDGE_MODEL,
                # The judge is a reasoning model. It emits reasoning tokens before
                # the verdict, so the budget must cover reasoning PLUS the answer.
                # At 8 tokens every call came back finish_reason="length" with
                # empty content and the unparseable case used to fall through to
                # "TIE" -- which is how a run reported 100% ties while grading
                # nothing at all.
                max_completion_tokens=JUDGE_MAX_TOKENS,
                temperature=0,
                messages=[
                    {"role": "system", "content": PAIRWISE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Question:\n{query[:1200]}\n\n"
                            f"--- Answer A ---\n{answer_a[:JUDGE_ANSWER_CHARS]}\n\n"
                            f"--- Answer B ---\n{answer_b[:JUDGE_ANSWER_CHARS]}"
                        ),
                    },
                ],
            )
            break
        except Exception as e:
            last_err = e
            # Shared daily cap: back off rather than silently dropping the sample.
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 20 * (attempt + 1)
                print(f"    judge rate limited, retry {attempt + 1}/{JUDGE_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            print(f"    judge error: {e}")
            return "ERROR"
    else:
        print(f"    judge gave up after {JUDGE_RETRIES} attempts: {last_err}")
        return "ERROR"

    choice = resp.choices[0]
    if choice.finish_reason == "length":
        # Ran out of budget mid-reasoning. Unknown verdict, NOT a tie.
        print(f"    judge truncated at {JUDGE_MAX_TOKENS} tokens")
        return "ERROR"

    text = (choice.message.content or "").strip().upper()
    # The verdict is the last standalone token; earlier text can be prose that
    # happens to contain a letter.
    for token in reversed(text.replace("\n", " ").split()):
        bare = token.strip(".,:;!?*\"'()[]")
        if bare in ("A", "B", "TIE"):
            return bare
    # Unparseable. Never default this to TIE -- a judge we could not read is a
    # dropped sample, and reporting it as a tie manufactures agreement.
    print(f"    judge output unparseable: {text[:80]!r}")
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


# Queries that point at context which is not actually in the text. The gold CSV
# strips the source passage, so these read "Given this paragraph, ..." with no
# paragraph. Both models then guess or ask for the text, and grading that pair
# measures nothing. 86 of 8618 eligible queries are affected.
MISSING_CONTEXT_PATTERNS = (
    (r"\b(?:given|according to|based on|from|using)\s+(?:this|these|the\s+following|"
     r"the\s+above)\s+(?:paragraph|passage|text|article|document|excerpt|table|chart|"
     r"snippet|graph)s?\b", "references a paragraph/passage"),
    (r"\b(?:this|these|the\s+following|the\s+above)\s+"
     r"(?:paragraph|passage|text|article|excerpt|table|chart|snippet)s?\s*[:,]",
     "references a passage, colon"),
    (r"\bin\s+your\s+(?:community|city|town|area|neighborhood|local\s+area)\b",
     "needs user location"),
)

# "the following definition:", "collecting the given data." -- a pointer to
# content that should follow it and is not there. Anchored at the END of the
# query so that self-contained phrasing like "remove duplicates from a given
# list of numbers" is NOT swept up.
ABSENT_CONTENT_NOUNS = (
    r"definition|data|list|text|statement|steps|requirements|countries|code|"
    r"paragraph|passage|article|excerpt|table|chart|image|document|snippet|"
    r"question|scenario|context|information|details|description|transcript"
)
DANGLING_POINTER = re.compile(
    r"\b(?:the\s+)?(?:following|given|above|provided|attached)\s+"
    r"(?:" + ABSENT_CONTENT_NOUNS + r")s?\s*[:.]?\s*$", re.I)


def missing_context(query: str) -> str | None:
    t = " ".join((query or "").split())
    if len(t) >= 400:
        return None  # long enough that the context is probably embedded
    for pat, why in MISSING_CONTEXT_PATTERNS:
        if re.search(pat, t, re.I):
            return why
    # A dangling pointer at the very end promises content that never arrives.
    if DANGLING_POINTER.search(t):
        return "dangling reference to content that is absent"
    return None


def load_queries_from_gold(
    n: int, seed: int, bands=("easy", "mid", "hard")
) -> tuple[list[str], dict[str, int]]:
    """Sample from the Claude-gold holdout, stratified by difficulty.

    This is the set the emma numbers come from, so the comparison is drawn from
    the same distribution the product's accuracy claims describe -- not from
    whatever demo traffic happens to be in the request log.

    Stratifying matters for the conclusion, not just for rigour: the product does
    NOT claim the cheap tier matches frontier everywhere. It claims cheap is fine
    for easy queries and frontier earns its keep on hard ones. A flat random
    sample averages those two effects together and supports neither claim. Per-band
    win rates do.
    """
    import csv

    path = (
        REPO / "backend" / "dataset_pipeline" / "datasets"
        / "labeled_dataset" / "gold_labeled_queries.csv"
    )
    if not path.exists():
        return [], {}

    rows = []
    skipped_unanswerable = 0
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            q = (row.get("query") or "").strip()
            try:
                score = int(row.get("gold_score") or -1)
            except ValueError:
                continue
            # Skip the tiny/trivial prompts: they are one-word facts where any
            # model scores identically and they only dilute the signal.
            if len(q) < 25 or not (0 <= score <= 10):
                continue
            if missing_context(q):
                skipped_unanswerable += 1
                continue
            rows.append((q, score))

    if not rows:
        return [], {}

    # easy / mid / hard bands matching the router's own cut structure
    by_band = {"easy": [], "mid": [], "hard": []}
    for q, score in rows:
        if score <= 3:
            by_band["easy"].append((q, score))
        elif score <= 6:
            by_band["mid"].append((q, score))
        else:
            by_band["hard"].append((q, score))

    wanted = [b for b in ("easy", "mid", "hard") if b in bands]
    rng = random.Random(seed)
    # Split the budget evenly across the requested bands only. Asking for
    # --bands easy should spend the whole sample on easy, not a third of it.
    per_band = max(1, n // len(wanted))
    picked, gold = [], {}
    for name in wanted:
        pool = list(by_band[name])
        if not pool:
            print(f"  warning: gold pool has no '{name}' queries")
            continue
        rng.shuffle(pool)
        for q, score in pool[:per_band]:
            picked.append(q)
            gold[q] = score

    print(
        f"gold pool: {len(rows)} queries "
        f"(easy {len(by_band['easy'])}, mid {len(by_band['mid'])}, "
        f"hard {len(by_band['hard'])}); "
        f"skipped {skipped_unanswerable} with missing context"
    )
    if len(wanted) > 1:
        rng.shuffle(picked)
    return picked[:n], gold


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
    ap.add_argument("--queries", help="file with one query per line; else use the gold holdout")
    ap.add_argument("--from-db", action="store_true",
                    help="use logged traffic instead of the gold holdout "
                         "(traffic is unrepresentative -- prefer the gold set)")
    ap.add_argument("--tier-a", default=DEFAULT_TIER_A)
    ap.add_argument("--tier-b", default=DEFAULT_TIER_B)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="ab_report.json")
    ap.add_argument("--dump-samples", type=int, default=0,
                    help="write N blind pairs to a file for human checking")
    ap.add_argument("--bands", default="easy,mid,hard",
                    help="comma-separated gold difficulty bands to sample from "
                         "(easy,mid,hard). Use --bands easy to test the claim "
                         "that cheap is fine on the queries the router actually "
                         "sends to cheap.")
    ap.add_argument("--workers", type=int, default=6,
                    help="concurrent queries; keep modest, the judge shares a "
                         "daily token cap with the live quality judge")
    args = ap.parse_args()

    bands = tuple(b.strip() for b in args.bands.split(",") if b.strip())
    bad = [b for b in bands if b not in ("easy", "mid", "hard")]
    if bad:
        print(f"Unknown band(s): {', '.join(bad)} -- use easy, mid, hard.")
        return 1

    if not GROQ_JUDGE_API_KEY:
        print("GROQ_JUDGE_API_KEY is not set -- the judge cannot run.")
        print("Set it in backend/.env (the same key the live quality judge uses).")
        return 1

    from router.rate_limiter import call_with_failover

    gold: dict[str, int] = {}
    if args.queries:
        queries = load_queries_from_file(args.queries, args.n)
    elif args.from_db:
        queries = load_queries_from_db(args.n)
    else:
        queries, gold = load_queries_from_gold(args.n, args.seed, bands)
    if not queries:
        print("No queries found. Pass --queries <file> or check the gold dataset path.")
        return 1

    rng = random.Random(args.seed)
    client = _judge_client()
    rows = []
    blind_samples = []
    dropped = Counter()
    short_answers = Counter()

    print(f"Comparing {args.tier_a} vs {args.tier_b} on {len(queries)} queries, blind.\n")

    def run_one(i, q):
        """Grade one query. Returns (result_or_None, drop_reasons, short_counts)."""
        drops, shorts = Counter(), Counter()
        answers = {}

        # Both tiers in parallel: they are independent providers, so there is no
        # reason to pay for the latency twice.
        def ask(tier):
            try:
                r = call_with_failover(tier, q)
                return tier, (r.get("text") or "", float(r.get("cost_usd") or 0.0))
            except Exception as e:
                drops[f"{tier}_call_failed"] += 1
                return tier, ("", 0.0)

        with ThreadPoolExecutor(max_workers=2) as ex:
            for tier, val in ex.map(ask, (args.tier_a, args.tier_b)):
                answers[tier] = val

        for tier in (args.tier_a, args.tier_b):
            # Only a genuinely EMPTY answer is ungradeable. A short answer can be a
            # perfectly correct one ("August 19, 2021"), so dropping everything
            # under MIN_ANSWER_CHARS silently deleted cheap's best-case wins and
            # biased the run in cheap's favour. Count them, judge them anyway.
            n = len(answers[tier][0].strip())
            if n == 0:
                drops[f"{tier}_empty"] += 1
            elif n < MIN_ANSWER_CHARS:
                shorts[tier] += 1

        if not answers[args.tier_a][0] or not answers[args.tier_b][0]:
            return None, drops, shorts

        # Randomise presentation order so position bias cancels. Seeded per query
        # so a concurrent run grades the same pairs in the same order every time.
        qrng = random.Random(f"{args.seed}:{q}")
        swap = qrng.random() < 0.5
        first, second = (args.tier_b, args.tier_a) if swap else (args.tier_a, args.tier_b)
        try:
            verdict = pick_winner(client, q, answers[first][0], answers[second][0])
        except BlankAnswer:
            drops["ungradeable_pair"] += 1
            return None, drops, shorts
        except Exception:
            drops["judge_failed"] += 1
            return None, drops, shorts

        if verdict == "ERROR":
            drops["judge_error"] += 1
            return None, drops, shorts
        if verdict == "TIE":
            winner = "TIE"
        elif verdict == "A":
            winner = first
        else:
            winner = second

        return ({
            "query": q,
            "winner": winner,
            "gold_score": gold.get(q),
            "answer_a_chars": len(answers[first][0]),
            "answer_b_chars": len(answers[second][0]),
            "cheap_cost": answers[args.tier_a][1],
            "other_cost": answers[args.tier_b][1],
        }, first, second, answers), drops, shorts

    # Concurrency is bounded because the judge shares a 200k token/day cap with
    # the live quality judge; going wide just burns the budget on 429s.
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(run_one, i, q): i for i, q in enumerate(queries, 1)}
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                payload, drops, shorts = fut.result()
            except Exception as e:
                dropped["worker_crashed"] += 1
                print(f"  [{i}/{len(queries)}] crashed: {e}")
                continue
            dropped.update(drops)
            short_answers.update(shorts)
            if payload is None:
                continue
            row, first, second, answers = payload
            rows.append(row)
            if len(blind_samples) < args.dump_samples:
                blind_samples.append({
                    "query": row["query"],
                    "answer_a": answers[first][0],
                    "answer_b": answers[second][0],
                })
            mark = "=" if row["winner"] == "TIE" else ("<" if row["winner"] == args.tier_a else ">")
            print(f"  [{i}/{len(queries)}] {mark} {row['winner']}")

    rows.sort(key=lambda r: r["query"])

    if not rows:
        print("No comparable rows -- every call failed.")
        print("Dropped reasons:", dict(dropped))
        return 1

    # A run where most pairs never got graded is not a result. Refuse to write it.
    attempted = len(queries)
    if len(rows) < attempted * 0.6:
        print(
            f"\nREFUSING TO WRITE {args.out}: only {len(rows)}/{attempted} pairs were "
            f"graded. That is not a measurement."
        )
        print("Dropped reasons:", dict(dropped))
        return 1

    n = len(rows)
    counts = Counter(r["winner"] for r in rows)
    cheap_wins = counts.get(args.tier_a, 0)
    other_wins = counts.get(args.tier_b, 0)
    ties = counts.get("TIE", 0)
    cost_a = sum(r["cheap_cost"] for r in rows)
    cost_b = sum(r["other_cost"] for r in rows)

    # Per-difficulty-band win rates. This is the number that actually supports the
    # product: cheap should hold up on easy queries and lose on hard ones.
    def band_of(score):
        if score is None:
            return "unknown"
        if score <= 3:
            return "easy"
        if score <= 6:
            return "mid"
        return "hard"

    by_band = {}
    for r in rows:
        b = by_band.setdefault(band_of(r.get("gold_score")), {"n": 0, args.tier_a: 0, args.tier_b: 0, "TIE": 0})
        b["n"] += 1
        b[r["winner"]] = b.get(r["winner"], 0) + 1
    for b in by_band.values():
        held = b[args.tier_a] + b.get("TIE", 0)
        b["win_or_tie_pct"] = round(held / b["n"] * 100, 1) if b["n"] else None

    report = {
        "n_compared": n,
        "n_attempted": attempted,
        "dropped": dict(dropped),
        "short_answers_counted_not_dropped": dict(short_answers),
        "tier_a": args.tier_a,
        "tier_b": args.tier_b,
        "bands_sampled": list(bands) if not args.queries and not args.from_db else "custom",
        "judge_model": GROQ_JUDGE_MODEL,
        "judge_max_tokens": JUDGE_MAX_TOKENS,
        "judge_answer_chars": JUDGE_ANSWER_CHARS,
        "seed": args.seed,
        "wins": {args.tier_a: cheap_wins, args.tier_b: other_wins, "TIE": ties},
        "cheap_win_pct": round(cheap_wins / n * 100, 1),
        "cheap_win_or_tie_pct": round((cheap_wins + ties) / n * 100, 1),
        "by_difficulty_band": by_band,
        "total_cost_a_usd": round(cost_a, 6),
        "total_cost_b_usd": round(cost_b, 6),
        "cost_ratio_b_over_a": round(cost_b / cost_a, 2) if cost_a else None,
        "note": (
            "Judge never saw which tier produced which answer, and the two answers "
            "were shown in randomised order. Cheap win-or-tie is the headline "
            "quality-retention number; a tie is not proof of parity. Queries are "
            "stratified from the Claude-gold holdout by difficulty -- read "
            "by_difficulty_band, not the flat average."
        ),
    }

    print("\n" + "=" * 58)
    print(f"{args.tier_a} wins : {cheap_wins:>4}  ({report['cheap_win_pct']}%)")
    print(f"{args.tier_b} wins : {other_wins:>4}  ({round(other_wins / n * 100, 1)}%)")
    print(f"ties            : {ties:>4}  ({round(ties / n * 100, 1)}%)")
    print(f"win or tie      : {report['cheap_win_or_tie_pct']}%")
    print(f"cost {args.tier_a:<8}: ${cost_a:.5f}   cost {args.tier_b}: ${cost_b:.5f}"
          f"   ratio {report['cost_ratio_b_over_a']}x")
    print("-" * 58)
    print(f"{args.tier_a} win-or-tie by difficulty band:")
    for name in ("easy", "mid", "hard", "unknown"):
        b = by_band.get(name)
        if not b:
            continue
        print(f"  {name:<8} n={b['n']:<4} win-or-tie {b['win_or_tie_pct']:>5}%"
              f"   ({args.tier_a} {b[args.tier_a]}, {args.tier_b} {b[args.tier_b]},"
              f" tie {b.get('TIE', 0)})")
    if dropped:
        print("-" * 58)
        print("dropped:", dict(dropped))
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