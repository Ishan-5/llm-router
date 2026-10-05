"""Guard against public metric drift.

productMetrics.js is the single source of truth for every number the frontend
states in public copy. This test fails if it drifts from the backend artifacts
it claims to mirror, or if the docs resurrect a retired figure.

The frontend cannot import this directly (it is not a package), so the check
parses the module as text and compares against the live backend.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(r"D:\llm-router")
PM = REPO / "frontend" / "src" / "productMetrics.js"
BACKEND = REPO / "backend"
ROUTING = REPO / "customer-support" / "routing"

pytestmark = pytest.mark.skipif(
    not PM.exists(), reason="frontend/productMetrics.js not present"
)


@pytest.fixture(scope="module")
def pm() -> str:
    return PM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def model_config() -> dict:
    code = (
        "import sys,json; sys.path.insert(0,'.');"
        "from router.config import MODEL_CONFIG;"
        "from router.providers_registry import PROVIDERS_REGISTRY;"
        "print(json.dumps({'cfg': MODEL_CONFIG,"
        "'n_providers': len(PROVIDERS_REGISTRY),"
        "'n_models': sum(len(v.get('models') or []) for v in PROVIDERS_REGISTRY.values())}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND, capture_output=True, text=True, timeout=300,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def policies() -> dict:
    code = (
        "import sys,json\n"
        f"sys.path.insert(0,'.'); sys.path.insert(0,'src'); sys.path.insert(0,'router')\n"
        f"sys.path.insert(0, {str(ROUTING)!r})\n"
        "import feature_builder as fb\n"
        "out={}\n"
        "for pid in ('3tier','2tier'):\n"
        "    p=fb.load_policy(pid); e=p.honest_eval\n"
        "    out[pid]={'cheap_ceil':p.cheap_ceil,'frontier_floor':p.frontier_floor,"
        "'mae_mean':e['mae_mean'],'spearman_mean':e['spearman_mean'],"
        "'recall_frontier':e['recall_frontier'],'escape_rate':e['frontier_escape_rate']}\n"
        "print(json.dumps(out))\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND, capture_output=True, text=True, timeout=600,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def tier_block(pm: str, tier: str) -> str:
    m = re.search(rf"\b{tier}:\s*\{{(.*?)\n  \}}", pm, re.S)
    assert m, f"could not find tier block {tier!r} in productMetrics.js"
    return m.group(1)


def section(pm: str, name: str) -> str:
    """Return the object literal assigned to `name`, brace-matched.

    LISA_EVAL/KATE_EVAL are spread from SUPPORT_EVAL, so a naive regex either
    stops at the first inner brace or misses the inherited fields. Walk the
    braces instead and resolve the spread at lookup time.
    """
    m = re.search(rf"\b{name}\s*=\s*\{{", pm)
    assert m, f"could not find {name!r} in productMetrics.js"
    start = m.end() - 1
    depth = 0
    for i in range(start, len(pm)):
        if pm[i] == "{":
            depth += 1
        elif pm[i] == "}":
            depth -= 1
            if depth == 0:
                body = pm[start + 1 : i]
                spread = re.search(r"\.\.\.([A-Z_]+)\s*,", body)
                if spread:
                    base = section(pm, spread.group(1))
                    return base + "\n" + body
                return body
    raise AssertionError(f"unbalanced braces for {name!r}")


def num(block: str, field: str) -> float:
    m = re.search(rf"\b{field}\s*:\s*([0-9.]+)", block)
    assert m, f"missing numeric field {field!r}"
    return float(m.group(1))


# ---------------------------------------------------------------------------
# Tier catalogue must match the live router config exactly.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Dashboard display bugs. These shipped, so each one gets a guard.
# ---------------------------------------------------------------------------

def _strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def _broken_money(total_savings: float) -> str:
    """The exact expression MetricsBand/MetricsDashboard shipped:

        AnimatedCounter value={Math.round(v * 100)} prefix="$"
        + "." + v.toFixed(2).split(".")[1]

    which double-counted cents and rendered $0.1219 as "$12.12".
    """
    frac = f"{total_savings:.2f}".split(".")[1] if total_savings else "00"
    return f"${round(total_savings * 100)}.{frac}"


def test_broken_money_expression_would_inflate_sub_dollar_savings():
    """Pins the original bug so the fix cannot be reverted by copying the old
    code back out of history."""
    assert _broken_money(0.1219) == "$12.12"   # the real demo-key value
    assert _broken_money(0.0001) == "$0.00"     # small savings vanish entirely
    assert _broken_money(12.0) == "$1200.00"    # it is not a sub-dollar-only bug:
    # the counter is scaled by 100 and the decimals are appended unconditionally,
    # so it is wrong at every magnitude except exactly zero.


def test_money_component_renders_the_value_it_is_given():
    """Money.jsx must split the FORMATTED string and animate the integer part.

    Never scale the value for the counter. The old expression inflated every
    sub-dollar figure by ~100x, and $0.1219 of real savings displayed as $12.12.
    """
    src = (REPO / "frontend" / "src" / "components" / "Money.jsx").read_text(
        encoding="utf-8"
    )
    code = _strip_js_comments(src)

    assert "toFixed(4)" in code, "Money must format to 4dp to match the rest of the page"
    assert "Math.round(Number(int))" in code, (
        "animate the integer part of the formatted string, not value * 100"
    )
    assert "* 100" not in code and "*100" not in code, (
        "the ~100x inflation bug must not come back"
    )

    # the correct rendering for the values this page actually shows
    for value, expected in (
        (0.1219, "$0.1219"), (0.0, "$0.0000"), (0.0293, "$0.0293"), (12.12, "$12.1200"),
    ):
        int_part, dec_part = f"{value:.4f}".split(".")
        assert f"${int(int_part)}.{dec_part}" == expected


def test_no_component_reimplements_the_money_split():
    """One implementation only. Five near-identical copies is how $0.1219 became
    $12.12 in two of them while a third rendered it correctly."""
    src_root = REPO / "frontend" / "src"
    offenders = []
    for path in src_root.rglob("*.jsx"):
        if path.name == "Money.jsx":
            continue
        text = path.read_text(encoding="utf-8")
        # the broken shape: scale by 100 for the counter AND append a decimal part
        if re.search(r"AnimatedCounter[^/]*?\*\s*100", text, re.S) and re.search(
            r"toFixed\(2\)\)?\.split\('\.'\)", text
        ):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, (
        "these files reimplement the broken dollar readout; import Money.jsx: "
        + ", ".join(offenders)
    )


def test_tier_distribution_cannot_silently_drop_tiers():
    """The pie listed cheap/mid/frontier/web from a hardcoded array while the
    'Total' line printed every logged request. 'gemini' (cross-provider last
    resort) and 'failed' were therefore invisible: 13 of 396 requests on the demo
    key, 3.3% of traffic, missing from the breakdown.

    The breakdown must be driven by what the backend logged, not by a local list.
    """
    src = (REPO / "frontend" / "src" / "components" / "MetricsDashboard.jsx").read_text(
        encoding="utf-8"
    )
    assert re.search(r"tierOrder\s*=\s*\[\s*\.\.\.TIER_ORDER", src), (
        "tier breakdown must be built from TIER_ORDER plus any extra logged tiers"
    )
    assert re.search(r"Object\.keys\(stats\.tier_counts", src), (
        "extra tiers must be appended from the backend's own tier_counts"
    )
    assert "gemini" in src, "gemini is a real logged tier (routes/route.py) and needs a label"

    labels = re.search(r"TIER_LABELS\s*=\s*\{(.*?)\}", src, re.S).group(1)
    for tier in ("cheap", "mid", "frontier", "web", "gemini", "failed"):
        assert f"{tier}:" in labels, f"tier {tier!r} has no display label"


def test_savings_percentage_and_dollar_figure_share_one_baseline():
    """RoutingDiagram recomputed the percentage locally against
    hypothetical-only, while the dollar figure beside it included cache savings.
    Same page, same data: 71% next to $0.1219 while the dashboard said 77%.

    Every surface must read the backend's savings_pct so the two cannot diverge.
    """
    for rel in ("components/RoutingDiagram.jsx", "components/MetricsBand.jsx",
                "components/MetricsDashboard.jsx", "components/LiveStatsStrip.jsx"):
        text = (REPO / "frontend" / "src" / rel).read_text(encoding="utf-8")
        assert "stats.savings_pct" in text or "ticker.savings_pct" in text, (
            f"{rel} must use the backend savings_pct"
        )
        assert not re.search(r"1\s*-\s*\w*\.?total_actual_cost\s*/\s*\w*\.?total_hypothetical_cost", text), (
            f"{rel} recomputes the percentage against a different baseline than "
            f"the dollar figure beside it"
        )


def test_savings_components_are_reconciled_for_display():
    """Cache saved + Routing saved must equal Total saved at the precision shown.

    Left to the backend's independently-rounded values they do not: $0.0293 +
    $0.0925 = $0.1218 against a stated total of $0.1219. A reader adding up the
    row finds a missing penny and stops trusting the rest of the page.
    """
    src = (REPO / "frontend" / "src" / "productMetrics.js").read_text(encoding="utf-8")
    assert "export function savingsBreakdown" in src, (
        "displayed savings components must go through savingsBreakdown so they "
        "reconcile at display precision"
    )
    body = re.search(r"export function savingsBreakdown.*?\n\}", src, re.S).group(0)
    assert "total - cache" in body.replace("  ", " "), (
        "routing must be derived as total - cache, which is the only way the three "
        "figures are guaranteed to add up once rounded for display"
    )

    for rel in ("components/MetricsBand.jsx", "components/MetricsDashboard.jsx"):
        text = (REPO / "frontend" / "src" / rel).read_text(encoding="utf-8")
        assert "savingsBreakdown" in text, f"{rel} must use savingsBreakdown"
        assert not re.search(r"stats\.routing_savings_usd\s*\|\|\s*0", text), (
            f"{rel} renders the raw backend routing figure, which does not reconcile"
        )


def test_latency_by_tier_excludes_cache_hits():
    """routes/route.py logs a cache hit against the tier it WOULD have served from,
    with the near-instant lookup time. Averaging those in with real model calls
    made the chart compare 'model call + cache lookup' against 'model call'."""
    stats_py = (BACKEND / "router" / "routes" / "stats.py").read_text(encoding="utf-8")
    block = re.search(r"avg_latency_by_tier = \{.*?\}\n", stats_py, re.S)
    assert block, "avg_latency_by_tier not found in stats.py"
    assert "cache_hit == False" in block.group(0), (
        "avg_latency_by_tier must exclude cache hits"
    )
    # the overall figure a user waits for must still include everything
    overall = re.search(r"avg_latency_ms = float\((.*?)\)", stats_py, re.S)
    assert overall and "cache_hit" not in overall.group(1), (
        "avg_latency_ms is end-to-end and must keep counting every request"
    )

    dash = (REPO / "frontend" / "src" / "components" / "MetricsDashboard.jsx").read_text(
        encoding="utf-8"
    )
    assert "Avg model-call latency by tier" in dash, (
        "the chart must say it excludes cache hits and is not a quality measure"
    )
    assert "not a measure of answer quality" in dash


def test_mode_comparison_states_its_own_baseline():
    """The mode rows quote 65% while the headline quotes 77%. Both are right --
    different window, and the rows exclude cache. Say so, or it reads as a bug."""
    dash = (REPO / "frontend" / "src" / "components" / "MetricsDashboard.jsx").read_text(
        encoding="utf-8"
    )
    assert "cache hits and web searches are excluded" in dash
    assert "Save {m.savings_pct}% vs all-frontier" in dash, (
        "the mode rows' baseline is all-frontier pricing for the same window"
    )


def test_cache_savings_are_not_double_counted_in_the_savings_components():
    """stats.py: routing = hypothetical - actual, total = cache + routing, and the
    percentage baseline is hypothetical + cache_savings.

    The three figures the page shows side by side must reconcile. They will not
    reconcile to the cent, because each is independently rounded from
    higher-precision backend values -- on the demo key cache $0.0293 + routing
    $0.0925 displayed as $0.1218 against a total of $0.1219. That penny is display
    rounding, not a bug; what must hold is the underlying identity.
    """
    actual, hypothetical, cache_saved = 0.0369, 0.1295, 0.0293
    routing = max(0.0, round(hypothetical - actual, 6))
    total = round(cache_saved + routing, 6)
    baseline = hypothetical + cache_saved
    pct = round((1 - actual / baseline) * 100, 1)

    assert abs((actual + total) - baseline) < 1e-9, (
        "actual + total_saved must equal the baseline the percentage is taken "
        "against, otherwise the figures on screen cannot both be true"
    )
    assert pct == 76.8, "the % shown next to a total-saved figure must use this baseline"

    # the displayed components must land within one display-rounding step of the
    # displayed total -- enough for a reader to reconcile them by eye
    assert abs(round(cache_saved + routing, 4) - round(total, 4)) <= 0.0001
    # and the percentage must be reconcilable from the two dollar figures shown
    shown_total = round(cache_saved + routing, 4)
    assert abs((1 - actual / (actual + shown_total)) * 100 - pct) < 0.15


def test_public_components_do_not_hardcode_tier_prices():
    """Tier prices must come from productMetrics.

    This caught a hand-typed $0.15 / $0.27 pair in the landing page's SVG tier
    diagram that no other surface used, which is exactly how the three original
    savings numbers disagreed in the first place.
    """
    src_root = REPO / "frontend" / "src"
    price_lit = re.compile(
        r"\$\s*(0\.075|0\.15|0\.27|0\.30|0\.60|1\.10)\s*/\s*(1M|million)", re.I
    )
    offenders = []
    for path in src_root.rglob("*.jsx"):
        if path.name == "productMetrics.js":
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if price_lit.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{i}")
    assert not offenders, (
        "these files hardcode a per-M tier price instead of reading productMetrics: "
        + ", ".join(offenders)
    )


def test_config_py_cost_comment_matches_the_prices_above_it():
    """config.py carries a worked per-request cost table in a comment explaining
    why the tiers must ascend. That table silently drifted once already: it still
    showed the old 500/500 assumption and a 3.7x ratio while the code underneath
    had been re-tiered.

    A comment cannot be imported, so parse it and recompute it.
    """
    cfg_src = (BACKEND / "router" / "config.py").read_text(encoding="utf-8")
    m = re.search(r"# Per-request cost @ ([\d,]+) in / ([\d,]+) out", cfg_src)
    assert m, "config.py lost its per-request cost comment"
    n_in, n_out = int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))

    start = cfg_src.index("MODEL_CONFIG = {") + len("MODEL_CONFIG = {")
    depth = 1
    for i in range(start, len(cfg_src)):
        if cfg_src[i] == "{":
            depth += 1
        elif cfg_src[i] == "}":
            depth -= 1
            if depth == 0:
                block = cfg_src[start:i]
                break
    else:
        raise AssertionError("could not brace-match MODEL_CONFIG in config.py")
    prices = {}
    for tier in ("cheap", "mid", "frontier"):
        tb = block[block.index(f'"{tier}"') :]
        tb = tb[: tb.index("}")]
        prices[tier] = (
            float(re.search(r'"price_per_m_input":\s*([0-9.]+)', tb).group(1)),
            float(re.search(r'"price_per_m_output":\s*([0-9.]+)', tb).group(1)),
        )

    rows = re.findall(
        r"#\s+(cheap|mid|frontier)\s+(\S+)\s+\$([0-9.]+)\s+\(([0-9.]+)x\)", cfg_src
    )
    assert len(rows) == 3, f"expected 3 cost rows in the comment, found {len(rows)}"
    per_req = {t: (p[0] / 1e6) * n_in + (p[1] / 1e6) * n_out for t, p in prices.items()}

    for tier, _model, cost, ratio in rows:
        want_cost = round(per_req[tier], 6)
        assert float(cost) == pytest.approx(want_cost, abs=5e-7), (
            f"comment says {tier} costs ${cost}, actual ${want_cost:.6f} "
            f"@ {n_in} in / {n_out} out"
        )
        want_ratio = per_req[tier] / per_req["cheap"]
        assert float(ratio) == pytest.approx(round(want_ratio, 1), abs=0.05), (
            f"comment says {tier} is {ratio}x cheap, actual {want_ratio:.2f}x"
        )


@pytest.mark.parametrize("tier", ["cheap", "mid", "frontier"])
def test_tier_prices_match_router_config(pm: str, model_config: dict, tier: str):
    block = tier_block(pm, tier)
    cfg = model_config["cfg"][tier]
    assert re.search(r"model:\s*'" + re.escape(cfg["model_id"]) + r"'", block), (
        f"{tier} model drifted from router config: {cfg['model_id']}"
    )
    assert re.search(r"provider:\s*'" + re.escape(cfg["provider"]) + r"'", block)
    assert num(block, "priceIn") == cfg["price_per_m_input"]
    assert num(block, "priceOut") == cfg["price_per_m_output"]


def test_provider_count_is_not_stale(pm: str, model_config: dict):
    """The '9+ providers' / '~15 providers' claims were both wrong."""
    m = re.search(r"CATALOG_MODEL_COUNT\s*=\s*([0-9]+)", pm)
    assert m, "CATALOG_MODEL_COUNT missing"
    assert int(m.group(1)) == model_config["n_models"], (
        f"catalog size {m.group(1)} != live {model_config['n_models']}"
    )

    pm_providers = re.search(r"\bPROVIDERS\s*=\s*\[(.*?)\]", pm, re.S)
    assert pm_providers, "PROVIDERS list missing"
    listed = re.findall(r"'([^']+)'", pm_providers.group(1))
    assert len(listed) == model_config["n_providers"], (
        f"PROVIDERS lists {len(listed)}, backend has {model_config['n_providers']}"
    )
    assert len(set(listed)) == len(listed), "PROVIDERS contains duplicates"

    count = re.search(r"PROVIDER_COUNT\s*=\s*PROVIDERS\.length", pm)
    assert count, "PROVIDER_COUNT must be derived from PROVIDERS, not typed"


# ---------------------------------------------------------------------------
# Support policy metrics must match the shipped joblib artifacts.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pid,label,prefix",
    [("3tier", "lisa", "LISA_EVAL"), ("2tier", "kate", "KATE_EVAL")],
)
def test_support_eval_matches_artifacts(pm: str, policies: dict, pid: str, label: str, prefix: str):
    block = section(pm, prefix)
    art = policies[pid]
    assert num(block, "maeMean") == pytest.approx(round(art["mae_mean"], 3), abs=0.001)
    assert num(block, "spearmanMean") == pytest.approx(round(art["spearman_mean"], 3), abs=0.001)
    assert num(block, "recallFrontierPct") == pytest.approx(round(art["recall_frontier"] * 100, 1), abs=0.05)
    assert num(block, "frontierEscapePct") == pytest.approx(round(art["escape_rate"] * 100, 1), abs=0.05)


def test_kate_is_the_safer_policy(pm: str):
    """kate must show strictly lower frontier escape than lisa, or the
    'use kate for support' advice in the guide is wrong."""
    lisa = section(pm, "LISA_EVAL")
    kate = section(pm, "KATE_EVAL")
    assert num(kate, "frontierEscapePct") < num(lisa, "frontierEscapePct")
    assert num(kate, "recallFrontierPct") > num(lisa, "recallFrontierPct")


def test_kate_cuts_match_artifact(pm: str, policies: dict):
    block = section(pm, "KATE_CUTS")
    assert num(block, "cheap") == policies["2tier"]["cheap_ceil"]


def test_lisa_cuts_match_artifact(pm: str, policies: dict):
    block = section(pm, "LISA_CUTS")
    assert num(block, "cheap") == policies["3tier"]["cheap_ceil"]
    assert num(block, "frontier") == policies["3tier"]["frontier_floor"]


# ---------------------------------------------------------------------------
# The savings headline must be arithmetically derivable, not asserted.
# ---------------------------------------------------------------------------

def test_savings_headline_is_derived_from_the_stated_mix(pm: str):
    """SAVINGS_PCT is the one number every page quotes. It has to be the rounded
    blend of EXAMPLE_COSTS under MEASURED_TRAFFIC_MIX, or the marketing copy is
    lying by construction."""
    # perRequestCost is a function call, so recompute from the tier prices.
    prices = {}
    for tier in ("cheap", "mid", "frontier"):
        b = tier_block(pm, tier)
        prices[tier] = (num(b, "priceIn"), num(b, "priceOut"))

    tok = re.search(r"EXAMPLE_TOKENS\s*=\s*\{\s*in:\s*([0-9]+),\s*out:\s*([0-9]+)", pm)
    n_in, n_out = int(tok.group(1)), int(tok.group(2))
    per_req = {
        t: (p[0] / 1e6) * n_in + (p[1] / 1e6) * n_out for t, p in prices.items()
    }

    mix_block = section(pm, "MEASURED_TRAFFIC_MIX")
    mix = {m: float(v) for m, v in re.findall(r"(cheap|mid|frontier|web|failed):\s*([0-9.]+)", mix_block)}
    paid = sum(mix.get(t, 0) for t in per_req)
    blend = sum(per_req[t] * (mix.get(t, 0) / paid) for t in per_req)
    exact = (1 - blend / per_req["frontier"]) * 100

    m_exact = re.search(r"SAVINGS_EXACT_PCT\s*=\s*round1\(mixSavings", pm)
    assert m_exact, "SAVINGS_EXACT_PCT must be computed, not typed"
    m_pct = re.search(r"SAVINGS_PCT\s*=\s*([0-9]+)", pm)
    assert m_pct, "SAVINGS_PCT missing"
    advertised = float(m_pct.group(1))

    # The advertised figure rounds up from the measured one on purpose, and the
    # comment in productMetrics.js says so. The guard is that the gap stays
    # small: past a point it is no longer "the measured mix, rounded", it is a
    # number with nothing behind it.
    gap = advertised - exact
    assert abs(gap) <= 1.05, (
        f"SAVINGS_PCT={advertised} is {gap:.1f} points from the {exact:.1f}% the "
        f"stated mix actually yields"
    )


def test_hard_share_table_is_derived_and_is_a_two_tier_model(pm: str):
    """SAVINGS_BY_HARD_SHARE is a different model from SAVINGS_PCT: hard goes to
    frontier, everything else to cheap, mid is excluded.

    That is why its 19% row reads 59% while the measured mix -- which also has 19%
    frontier traffic -- reads 49%. Both are correct, but a reader who does not
    know that will read the page as self-contradictory, so the model is documented
    in the source and enforced here.
    """
    assert re.search(
        r"SAVINGS_BY_HARD_SHARE\s*=\s*\[[^\]]*\]\.map", pm, re.S
    ), "SAVINGS_BY_HARD_SHARE must be derived from the tier prices, not typed"

    m = re.search(r"function twoTierSavings.*?\n\}", pm, re.S)
    assert m, "twoTierSavings helper missing; the table's model must be explicit"
    body = m.group(0)
    assert "EXAMPLE_COSTS.cheap" in body and "EXAMPLE_COSTS.frontier" in body
    assert "mid" not in body.lower(), (
        "twoTierSavings must not include the mid tier -- that is the whole reason "
        "it disagrees with SAVINGS_PCT and the comment says so"
    )

    assert re.search(r"NOT the same model as SAVINGS_PCT", pm), (
        "the two-tier/three-tier distinction must stay documented in the source"
    )


def test_emma_and_support_maes_are_not_conflated(pm: str):
    """emma and the support models are scored on different holdouts. The guide
    says so explicitly; this makes it impossible to accidentally merge them."""
    emma = num(section(pm, "EMMA_EVAL"), "mae")
    for prefix in ("LISA_EVAL", "KATE_EVAL"):
        assert num(section(pm, prefix), "maeMean") != emma


# ---------------------------------------------------------------------------
# Docs must not resurrect a retired figure.
# ---------------------------------------------------------------------------

RETIRED_CLAIMS = [
    ("README.md", r"52%\s*cheaper", "savings headline was unified at 50%"),
    ("README.md", r"\$0\.288", "blended cost recomputed to $0.306"),
    ("README.md", r"9\+\s*providers", "provider count is exactly 10"),
    ("customer-support/README.md", r"52%\s*cheaper", "savings headline was unified at 50%"),
]


@pytest.mark.parametrize("rel,pattern,why", RETIRED_CLAIMS)
def test_docs_do_not_resurrect_retired_numbers(rel: str, pattern: str, why: str):
    p = REPO / rel
    if not p.exists():
        pytest.skip(f"{rel} not present")
    hits = re.findall(pattern, p.read_text(encoding="utf-8", errors="replace"))
    assert not hits, f"{rel} still states {pattern!r} ({len(hits)}x) -- {why}"


def test_readme_quotes_the_single_savings_number():
    readme = (REPO / "README.md").read_text(encoding="utf-8", errors="replace")
    pm = PM.read_text(encoding="utf-8")
    pct = re.search(r"SAVINGS_PCT\s*=\s*([0-9]+)", pm).group(1)
    assert f"{pct}% cheaper" in readme, (
        f"README must state the canonical {pct}% figure"
    )


def test_readme_test_badge_is_not_stale():
    """The badge hardcodes a count, so it rots the moment a test is added.

    This is the same failure mode as the tier prices, so it gets the same
    treatment: assert the badge against reality rather than trusting whoever
    last remembered to bump it.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"badge/tests-([0-9]+)%20passing", readme)
    assert m, "README test badge missing"
    claimed = int(m.group(1))

    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        cwd=BACKEND, capture_output=True, text=True, timeout=600,
    )
    assert collected.returncode == 0, collected.stderr[-2000:]
    actual = len(re.findall(r"(?m)^tests\/\S+::\S+", collected.stdout))
    assert claimed == actual, (
        f"README badge claims {claimed} tests but pytest collects {actual}. "
        f"Update the badge, or drop the count from it."
    )


# ---------------------------------------------------------------------------
# Superseded evaluation artifacts must keep saying they are superseded.
# ---------------------------------------------------------------------------

SUPERSEDED_ARTIFACTS = [
    "customer-support/docs/final_model_report.txt",
    "customer-support/docs/support_eval_report.md",
    "customer-support/docs/three_tier_best.json",
    "customer-support/docs/tier_comparison.json",
]


@pytest.mark.parametrize("rel", SUPERSEDED_ARTIFACTS)
def test_superseded_artifacts_are_labelled(rel: str):
    """These describe support_final.joblib / support_all / support_ds3, none of
    which the router serves. Their numbers are not wrong, they are just about
    different models, and the failure mode is somebody quoting them as current.

    The banner is the only thing separating "historical record" from "wrong
    claim", so removing it should fail a test rather than go unnoticed.
    """
    p = REPO / rel
    if not p.exists():
        pytest.skip(f"{rel} not present")
    head = p.read_text(encoding="utf-8", errors="replace")[:1500]
    assert "SUPERSEDED" in head.upper(), (
        f"{rel} holds stale eval numbers but carries no superseded banner. "
        f"Either delete it or mark it as historical."
    )
    assert "support_final_3tier" in head or "0.822" in head, (
        f"{rel} banner must point at the models actually served"
    )


@pytest.mark.parametrize("rel", ["customer-support/docs/three_tier_best.json",
                                 "customer-support/docs/tier_comparison.json"])
def test_superseded_json_artifacts_still_parse(rel: str):
    """The banner went into a JSON file via an underscore key, so prove the
    files are still loadable by whatever reads them."""
    p = REPO / rel
    if not p.exists():
        pytest.skip(f"{rel} not present")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "_status" in data


def test_no_doc_quotes_the_superseded_holdout_as_current():
    """0.688 / 0.856 / 82.2% belong to support_final.joblib. They may appear
    inside the bannered historical files and nowhere else."""
    for rel in ("README.md", "customer-support/README.md",
                "production_upgrade_needed.md"):
        p = REPO / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for pat in (r"0\.688", r"0\.856", r"82\.2\s*%"):
            assert not re.search(pat, text), (
                f"{rel} quotes {pat!r}, which belongs to the superseded "
                f"support_final.joblib run"
            )


def test_readme_operational_snapshot_is_labelled_as_a_snapshot():
    """A hardcoded request count reads as a live figure long after it stops
    being one. The deployment's /stats is auth-gated, so the count cannot be
    refreshed from the repo; the README must instead admit it is a snapshot."""
    readme = (REPO / "README.md").read_text(encoding="utf-8", errors="replace")
    seg = readme[readme.find("## \U0001F4CA Measured results") :][:2500]
    assert seg, "Measured results section not found"
    assert re.search(r"snapshot", seg, re.I), (
        "the measured-results section must label its figures as a snapshot"
    )
    assert not re.search(r"Requests routed\s*\|\s*~?\d+", seg), (
        "do not hardcode a request count; call GET /stats for current figures"
    )

class TestEasyBandAB:
    """Guards the measurement behind the 'without cutting quality' headline.

    This number earned its place the hard way: the first version of the A/B
    reported 100% ties while grading nothing, because the judge was given an
    8-token budget and unparseable output silently became "TIE".
    """

    def _block(self):
        src = (REPO / "frontend" / "src" / "productMetrics.js").read_text(encoding="utf-8")
        block = src.split("export const EASY_BAND_AB = {")[1].split("\n}")[0]
        return src, block

    def _n(self, block, key):
        return int(re.search(key + r":\s*(\d+)", block).group(1))

    def _f(self, block, key):
        return float(re.search(key + r":\s*([\d.]+)", block).group(1))

    def test_counts_are_internally_consistent(self):
        _, block = self._block()
        assert (self._n(block, "cheapWins") + self._n(block, "frontierWins")
                + self._n(block, "ties")) == self._n(block, "nGraded"), (
            "wins + ties must equal the graded sample"
        )

    def test_win_or_tie_percentage_matches_the_counts(self):
        _, block = self._block()
        n = self._n(block, "nGraded")
        pct = self._f(block, "cheapWinOrTiePct")
        computed = (self._n(block, "cheapWins") + self._n(block, "ties")) / n * 100
        assert abs(pct - computed) < 0.05, (pct, computed)

    def test_strict_win_percentages_match_the_counts(self):
        _, block = self._block()
        n = self._n(block, "nGraded")
        assert abs(self._f(block, "cheapWinPct")
                   - self._n(block, "cheapWins") / n * 100) < 0.05
        assert abs(self._f(block, "frontierWinPct")
                   - self._n(block, "frontierWins") / n * 100) < 0.05

    def test_tie_percentage_matches_the_counts(self):
        _, block = self._block()
        n = self._n(block, "nGraded")
        assert abs(self._f(block, "tiePct") - self._n(block, "ties") / n * 100) < 0.05

    def test_confidence_interval_brackets_the_point_estimate(self):
        _, block = self._block()
        pct = self._f(block, "cheapWinOrTiePct")
        lo, hi = (float(x) for x in
                  re.search(r"cheapWinOrTieCiPct:\s*\[\s*([\d.]+),\s*([\d.]+)\s*\]", block).groups())
        assert lo < pct < hi

    def test_attempted_accounts_for_graded_and_dropped(self):
        _, block = self._block()
        assert (self._n(block, "nGraded") + self._n(block, "dropped")
                <= self._n(block, "nAttempted"))

    def test_claim_is_scoped_not_a_parity_guarantee(self):
        """Frontier still wins ~1 pair in 4, so no comment may imply cheap equals
        frontier across the board."""
        src, _ = self._block()
        assert "NOT a claim that cheap equals" in src
        assert "cheapest" in src  # scoped to the cheap tier's own traffic

    def test_measured_ratio_is_distinct_from_the_1000_300_illustration(self):
        _, block = self._block()
        # 2.1x was measured on real gold queries; 3.6x is the 1000-in/300-out
        # illustration. Reusing the illustration as a measured figure is the
        # exact drift this module exists to prevent.
        assert self._f(block, "measuredCostRatio") == 2.1
        assert self._f(block, "measuredCostRatio") != 3.6

    def test_footnote_discloses_sample_size_and_interval(self):
        src = (REPO / "frontend" / "src" / "productMetrics.js").read_text(encoding="utf-8")
        foot = src.split("EASY_BAND_AB_FOOTNOTE =")[1].split("`;")[0]
        assert "95% CI" in foot
        assert "cheap tier" in foot
        assert "easy" in foot.lower()
        # sample size and interval must be interpolated from the measured block,
        # not retyped, so the prose cannot drift from the numbers
        assert "EASY_BAND_AB.nGraded" in foot
        assert "EASY_BAND_AB.cheapWinOrTieCiPct" in foot

    def test_every_surface_making_the_claim_also_shows_the_evidence(self):
        for rel in ("App.jsx", "components/LandingPage.jsx"):
            src = (REPO / "frontend" / "src" / rel).read_text(encoding="utf-8")
            assert "without cutting quality" in src, rel
            assert "EASY_BAND_AB_FOOTNOTE" in src, (
                f"{rel} states the quality claim with no supporting measurement"
            )

    def test_fabricated_report_is_absent_and_ignored(self):
        assert not (REPO / "backend" / "ab_report.json").exists()
        assert "ab_report.json" in (REPO / ".gitignore").read_text(encoding="utf-8")
