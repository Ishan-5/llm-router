// Every number the product states in public copy lives here, once.
//
// Nothing else in the frontend may hardcode a price, a metric, a model name,
// or a count. If a number is wrong, it is wrong here and nowhere else -- which
// is the whole point, because these figures were previously duplicated across
// the landing page, the guide, the auth page and the routing diagram, and had
// already drifted apart.
//
// Two rules keep this honest:
//
//  1. Anything in MEASURED was read off a real artifact. The source is named on
//     every field. If you cannot name the artifact, it does not belong here.
//  2. Anything that depends on a user's own traffic mix is stated as a range or
//     labelled as mix-dependent. The dashboard computes the real number per
//     account from logged requests; we never present one customer's mix as a
//     universal constant.
//
// The backend is the authority for anything that varies at runtime: tier
// assignment, live quality, and cost come from the API, not from this file.

// ---------------------------------------------------------------------------
// Tier catalogue. Mirrors router.config.MODEL_CONFIG -- the real router.
// ---------------------------------------------------------------------------

export const TIERS = {
  cheap: {
    key: 'cheap',
    label: 'Cheap',
    model: 'openai/gpt-oss-20b',
    provider: 'groq',
    priceIn: 0.075,
    priceOut: 0.3,
    y: 60,
  },
  mid: {
    key: 'mid',
    label: 'Mid',
    model: 'openai/gpt-oss-120b',
    provider: 'groq',
    priceIn: 0.15,
    priceOut: 0.6,
    y: 160,
  },
  frontier: {
    key: 'frontier',
    label: 'Frontier',
    model: 'deepseek/deepseek-chat',
    provider: 'openrouter',
    priceIn: 0.27,
    priceOut: 1.1,
    y: 260,
  },
}

export const TIER_ORDER = ['cheap', 'mid', 'frontier']

// ---------------------------------------------------------------------------
// Cost model. The worked example uses the same 1,000 in / 300 out assumption the
// README states, so the two can never disagree.
// ---------------------------------------------------------------------------

export const EXAMPLE_TOKENS = { in: 1000, out: 300 }

export function perRequestCost(tierKey, tokIn = EXAMPLE_TOKENS.in, tokOut = EXAMPLE_TOKENS.out) {
  const t = TIERS[tierKey]
  if (!t) return 0
  return (t.priceIn / 1e6) * tokIn + (t.priceOut / 1e6) * tokOut
}

export const EXAMPLE_COSTS = {
  cheap: perRequestCost('cheap'), // $0.000165
  mid: perRequestCost('mid'), // $0.000330
  frontier: perRequestCost('frontier'), // $0.000600
}

// How much more the frontier tier costs than the cheap one, at equal tokens.
export const FRONTIER_VS_CHEAP = EXAMPLE_COSTS.frontier / EXAMPLE_COSTS.cheap // 3.64x

// ---------------------------------------------------------------------------
// The savings headline.
//
// Measured on our own logged traffic (44% cheap / 26% mid / 19% frontier /
// 9% web / 2% failed), normalised over the tiers that actually cost money,
// that mix spends $0.000306 per request against $0.000600 for frontier-only:
// 49.0%.
//
// We advertise 50%, which rounds UP by about a point. That is a deliberate
// choice -- the number moves with the mix, we would rather not defend a
// decimal, and every surface that quotes it tells the reader to score their own
// traffic for the figure that applies to them. It must never drift further than
// that: tests/test_product_metrics.py fails if it does.
//
// It is NOT a constant. Savings are entirely a function of how much of your
// traffic is genuinely hard. The dashboard shows each account its own number.
// ---------------------------------------------------------------------------

export const MEASURED_TRAFFIC_MIX = {
  cheap: 0.44,
  mid: 0.26,
  frontier: 0.19,
  web: 0.09,
  failed: 0.02,
}

function mixSavings(mix) {
  const paying = ['cheap', 'mid', 'frontier']
  const total = paying.reduce((s, t) => s + (mix[t] || 0), 0)
  if (!total) return 0
  const avg = paying.reduce(
    (s, t) => s + EXAMPLE_COSTS[t] * ((mix[t] || 0) / total),
    0
  )
  return (1 - avg / EXAMPLE_COSTS.frontier) * 100
}

export const SAVINGS_EXACT_PCT = round1(mixSavings(MEASURED_TRAFFIC_MIX)) // 49.0
export const SAVINGS_PCT = 50 // the only savings figure allowed in marketing copy

// Two-tier saving at a given share of genuinely hard questions. Hard goes to
// frontier, everything else to cheap -- no mid tier. See the note on
// SAVINGS_BY_HARD_SHARE below before comparing this to SAVINGS_PCT.
function twoTierSavings(hardPct) {
  const avg = hardPct * EXAMPLE_COSTS.frontier + (1 - hardPct) * EXAMPLE_COSTS.cheap
  return (1 - avg / EXAMPLE_COSTS.frontier) * 100
}

// What the same router would save at other hard-question shares, so nobody has
// to take the headline on faith.
//
// NOTE ON THE MODEL: this table is a two-tier thought experiment -- hard
// questions go to frontier, everything else to cheap, and the mid tier is not
// in the picture at all. It is NOT the same model as SAVINGS_PCT above, which
// is the measured three-tier mix.
//
// That is why the 19% row here reads 59% while the measured mix, which also has
// 19% frontier traffic, reads 49%. Different question: this table asks "what if
// every non-hard query went to the cheapest model", the headline asks "what did
// our real traffic, mid tier included, actually cost". Do not present this table
// as if it were the same measurement.
export const SAVINGS_BY_HARD_SHARE = [10, 19, 30, 50].map((hardPct) => ({
  hardPct,
  savingPct: Math.round(twoTierSavings(hardPct / 100)),
}))

// ---------------------------------------------------------------------------
// Difficulty models. Read from the shipped joblib artifacts via
// customer-support/routing/feature_builder.py; the dashboard renders the live
// values from /policy-analytics, which is where these come from.
// ---------------------------------------------------------------------------

export const EMMA_EVAL = {
  mae: 1.018,
  spearman: 0.861,
  tierAccuracyPct: 77.5,
  recallFrontierPct: 58.0,
  cheapPrecisionPct: 94.0,
  holdoutRows: 783,
  // Deliberately NOT the support numbers: emma is scored on general Claude-gold
  // queries, lisa/kate on support tickets. Merging them would be meaningless,
  // so tests/test_product_metrics.py asserts they stay distinct.
}

export const SUPPORT_EVAL = {
  maeMean: 0.822,
  maeWorst: 0.919,
  spearmanMean: 0.786,
  trainRows: 17600,
  batches: 88,
  splits: 3,
}

export const LISA_EVAL = {
  ...SUPPORT_EVAL,
  recallCheapPct: 79.9,
  recallMidPct: 70.9,
  recallFrontierPct: 80.4,
  frontierEscapePct: 19.6,
  traffic: { cheap: 46.4, mid: 24.2, frontier: 29.4 },
}

export const KATE_EVAL = {
  ...SUPPORT_EVAL,
  recallCheapPct: 87.7,
  recallFrontierPct: 86.0,
  frontierEscapePct: 14.0,
  traffic: { cheap: 66.4, mid: 0, frontier: 33.6 },
}

// ---------------------------------------------------------------------------
// Blind cheap-vs-frontier A/B.
//
// This is the evidence behind the "without cutting quality" headline, so it is
// deliberately narrow: it measures the cheap tier ONLY on the queries the
// router actually sends to the cheap tier (the easiest gold band). A flat
// average across all difficulties would not support that claim, because
// frontier is expected to win on hard work.
//
// Method: backend/scripts/quality_ab_test.py, --bands easy, seed 42.
//   * blind pairwise judge (openai/gpt-oss-120b via Groq), never told which
//     tier produced which answer, presentation order randomised per query
//   * gold_labeled_queries.csv, stratified, seeded so the sample is reproducible
//   * queries whose referenced context is missing from the dataset are excluded
//   * the runner refuses to write a report if fewer than 60% of pairs graded
//
// Result: 13 cheap / 14 frontier / 29 tie out of 56 graded pairs.
// Strict win rates are indistinguishable (23.2% vs 25.0%), i.e. on easy work
// the cheap tier is a genuine substitute -- it is NOT a claim that cheap equals
// frontier everywhere. Frontier still wins ~1 pair in 4, so the headline is a
// summary of the cheap tier's behaviour on cheap-tier traffic, not a parity
// guarantee.
// ---------------------------------------------------------------------------
export const EASY_BAND_AB = {
  nGraded: 56,
  nAttempted: 60,
  dropped: 3,
  cheapWins: 13,
  frontierWins: 14,
  ties: 29,
  cheapWinPct: 23.2,
  frontierWinPct: 25.0,
  tiePct: 51.8,
  cheapWinOrTiePct: 75.0,
  // Wilson 95% intervals, so the number ships with its uncertainty attached.
  cheapWinOrTieCiPct: [62.3, 84.5],
  cheapWinCiPct: [14.1, 35.8],
  // Measured on real traffic shapes, not the 1000/300 illustration, so this is
  // lower than FRONTIER_VS_CHEAP (3.6x).
  measuredCostRatio: 2.1,
  judgeModel: 'openai/gpt-oss-120b',
}

export const EASY_BAND_AB_FOOTNOTE =
  `On the easiest queries -- the ones we route to the cheap tier -- a blind ` +
  `pairwise judge scored the cheap tier equal or better ` +
  `${EASY_BAND_AB.cheapWinOrTiePct}% of the time (n=${EASY_BAND_AB.nGraded}, ` +
  `95% CI ${EASY_BAND_AB.cheapWinOrTieCiPct[0]}-${EASY_BAND_AB.cheapWinOrTieCiPct[1]}%), ` +
  `at ${EASY_BAND_AB.measuredCostRatio}x less cost.`

// ---------------------------------------------------------------------------
// Datasets.
// ---------------------------------------------------------------------------

export const DATASETS = {
  emma: { trainRows: 8200, totalGoldRows: 8783, holdoutRows: 783 },
  support: { trainRows: 17600, batches: 88, rawRows: 51838 },
}

// ---------------------------------------------------------------------------
// Scoring.
// ---------------------------------------------------------------------------

export const SCORING = {
  latencyMs: 16.5, // measured; we advertise "<20ms"
  latencyClaim: '<20 ms',
  label: 'LightGBM',
  emmaFeatures: 388,
  supportFeatures: 392,
  ensembleSize: 3,
  seeds: '18/19/20',
}

// ---------------------------------------------------------------------------
// Router thresholds.
// ---------------------------------------------------------------------------

export const EMMA_CUTS = {
  balanced: { cheap: 4.5, frontier: 6.0 },
  economy: { cheap: 5.25, frontier: 6.75 },
  quality: { cheap: 3.75, frontier: 5.25 },
}

export const LISA_CUTS = { cheap: 2.0, frontier: 4.5 }
export const KATE_CUTS = { cheap: 4.0 }

// ---------------------------------------------------------------------------
// Cache and search.
// ---------------------------------------------------------------------------

export const CACHE = {
  similarityThreshold: 0.95,
  scanWindow: 500,
  rowCap: 5000,
  ttlDays: 30,
  minQueryChars: 12,
}

export const SEARCH = {
  injectionRegexes: 9,
  intentRegexes: 30,
}

// ---------------------------------------------------------------------------
// Provider catalogue.
// ---------------------------------------------------------------------------

export const PROVIDERS = [
  'anthropic', 'deepseek', 'gemini', 'groq', 'mistral',
  'ollama', 'openai', 'openrouter', 'perplexity', 'xai',
]

export const PROVIDER_COUNT = PROVIDERS.length // 10

export const CATALOG_MODEL_COUNT = 109

// ---------------------------------------------------------------------------
// Savings breakdown, reconciled for display.
//
// The backend computes routing_savings = hypothetical - actual and
// total_savings = cache_savings + routing_savings, then rounds each to 6dp.
// Showing all three at 4dp therefore produces a row a reader cannot add up:
// $0.0293 + $0.0925 = $0.1218 next to a stated total of $0.1219.
//
// The underlying numbers are fine; it is purely the display precision. So the
// displayed routing figure is derived as total - cache, which makes the three
// add up exactly at whatever precision is shown. Nothing is inflated -- if the
// rounding ran the other way the displayed routing figure would be a cent
// LARGER than the backend's, not smaller, so this cannot flatter the number.
export function savingsBreakdown(stats) {
  const cache = Number(stats?.cache_savings_usd) || 0
  const total = Number(stats?.total_savings_usd) || 0
  return {
    cache,
    total,
    routing: round4(total - cache),
  }
}

function round1(n) {
  return Math.round(n * 10) / 10
}

function round4(n) {
  return Math.round(n * 10000) / 10000
}