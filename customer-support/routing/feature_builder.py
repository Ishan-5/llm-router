"""Shared feature builder + policy loader for the customer-support difficulty models.

Two jobs:

1. build_support_features() produces the exact 392-column matrix the support
   regressors were trained on: MiniLM 384 + 4 handcrafted + 4 domain indicators.
   The layout is validated against the artifact manifest on every load, so a
   training/inference drift fails loudly at startup instead of silently
   mis-scoring traffic.

2. load_policy() / score_to_tier() resolve a policy id to a validated tier rule.
   The rule is read from the artifact, never inferred from n_tiers, so a future
   2-tier artifact with a stray mid band is a load-time error, not a production
   surprise.

The MiniLM embedder is imported from the generic router so the support path
reuses the one already resident in memory. Selecting a policy costs no extra
LLM call and no extra embedding pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO / "customer-support" / "models"

# --------------------------------------------------------------------------
# feature layout: the single source of truth for both artifacts
# --------------------------------------------------------------------------

EMBED_DIM = 384
HANDCRAFTED_NAMES = ("word_count", "has_code", "question_mark", "requested_length")
DOMAIN_ORDER = ("account_access", "delivery_general", "orders_billing", "technical")
FEATURE_COUNT = EMBED_DIM + len(HANDCRAFTED_NAMES) + len(DOMAIN_ORDER)
FEATURE_ORDER = "minilm384_then_handcrafted4_then_domain4"

_CODE_RE = re.compile(r"(?:def |function|class |import |SELECT |for\(|while\()")
_LENGTH_RE = re.compile(r"(\d+)[\s-]*word")

# --------------------------------------------------------------------------
# domain classification
# --------------------------------------------------------------------------
#
# The support models were trained with a domain one-hot, so inference needs one
# too. The public /route request carries no domain, so we derive it from the
# query text with a deterministic keyword vote. No model, no network, no extra
# latency, and the same input always yields the same domain.
#
# Order is fixed so the mapping is stable. When every bucket scores zero we fall
# back to delivery_general, the largest support domain, rather than an all-zero
# block the regressors never saw at training time.

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "account_access": (
        "password", "reset", "login", "log in", "sign in", "signin", "sign-in",
        "account", "locked out", "2fa", "two-factor", "mfa", "verify", "verification",
        "email confirmation", "username", "credentials", "sso", "otp", "authenticate",
        "access my", "can't log", "cannot log", "forgot",
    ),
    "orders_billing": (
        "order", "refund", "invoice", "billing", "charge", "charged", "payment",
        "subscription", "cancel my", "receipt", "price", "pricing", "discount",
        "coupon", "plan", "upgrade my", "downgrade", "renewal", "charged twice",
        "overcharged", "statement",
    ),
    "technical": (
        "error", "bug", "crash", "broken", "not working", "fails", "failing",
        "server", "api", "timeout", "connection", "network", "install", "setup",
        "installing", "update", "version", "device", "wifi", "bluetooth", "screen",
        "battery", "slow", "app won't", "app wont", "sync", "integration", "500",
        "400", "stack trace", "reboot", "restart", "driver", "firmware",
    ),
    "delivery_general": (
        "delivery", "shipping", "ship", "track", "tracking", "order status",
        "when will", "arrives", "package", "courier", "warehouse", "dispatch",
        "delayed", "missing item", "damaged",
    ),
}

DOMAIN_FALLBACK = "delivery_general"


def classify_domain(query: str) -> str:
    """Derive a support domain from query text with a deterministic keyword vote."""
    q = (query or "").lower()
    if not q.strip():
        return DOMAIN_FALLBACK
    best, best_hits = DOMAIN_FALLBACK, 0
    for domain in DOMAIN_ORDER:
        hits = sum(1 for kw in _DOMAIN_KEYWORDS[domain] if kw in q)
        if hits > best_hits:
            best, best_hits = domain, hits
    return best


def handcrafted(query: str) -> list[float]:
    """The 4 handcrafted features, identical to training and to the generic router."""
    word_count = len(query.split())
    has_code = int(bool(_CODE_RE.search(query)))
    question_mark = int("?" in query)
    m = _LENGTH_RE.search(query)
    requested_length = float(m.group(1)) if m else 0.0
    return [word_count, has_code, question_mark, requested_length]


def domain_block(domains: list[str]) -> np.ndarray:
    return np.array(
        [[1.0 if d == dom else 0.0 for dom in DOMAIN_ORDER] for d in domains], dtype=np.float32
    )


def build_support_features(embed: np.ndarray, queries: list[str], domains: list[str]) -> np.ndarray:
    """Assemble the 392-column matrix.

    embed must be (n, 384) MiniLM output. Raises if the shape or domain set
    drifts from what the artifacts were trained on.
    """
    embed = np.asarray(embed, dtype=np.float32)
    if embed.shape[0] != len(queries):
        raise ValueError(f"embed rows {embed.shape[0]} != queries {len(queries)}")
    if embed.ndim != 2 or embed.shape[1] != EMBED_DIM:
        raise ValueError(f"expected embed shape (n, {EMBED_DIM}), got {embed.shape}")
    if len(domains) != len(queries):
        raise ValueError(f"domains {len(domains)} != queries {len(queries)}")
    unknown = sorted({d for d in domains if d not in DOMAIN_ORDER})
    if unknown:
        raise ValueError(f"unknown domain(s) {unknown}; expected from {list(DOMAIN_ORDER)}")
    extra = np.array([handcrafted(q) for q in queries], dtype=np.float32)
    mat = np.hstack([embed, extra, domain_block(domains)])
    if mat.shape[1] != FEATURE_COUNT:
        raise ValueError(f"built {mat.shape[1]} features, expected {FEATURE_COUNT}")
    return mat


# --------------------------------------------------------------------------
# policies
# --------------------------------------------------------------------------

TIER2 = "tier2_single_cut"
TIER3 = "tier3_two_cuts"
VALID_RULES = {TIER2, TIER3}

POLICY_FILES = {
    "3tier": "support_final_3tier.joblib",
    "2tier": "support_final_2tier.joblib",
}
DEFAULT_POLICY = "3tier"

VALID_POLICIES = tuple(POLICY_FILES)


@dataclass(frozen=True)
class Policy:
    id: str
    n_tiers: int
    tier_rule: str
    cheap_ceil: float
    frontier_floor: float
    models: tuple
    feature_count: int
    domain_order: tuple
    honest_eval: dict

    @property
    def tiers(self) -> tuple[str, ...]:
        return ("cheap", "mid", "frontier") if self.n_tiers == 3 else ("cheap", "frontier")

    def tier_for(self, score: float) -> str:
        """Map a score to a tier using the artifact's own declared rule.

        tier2_single_cut:  cheap <= cheap_ceil, else frontier. No mid band.
        tier3_two_cuts:    cheap <= cheap_ceil, frontier >= frontier_floor,
                           else mid.
        """
        if self.tier_rule == TIER2:
            return "cheap" if score <= self.cheap_ceil else "frontier"
        if score <= self.cheap_ceil:
            return "cheap"
        if score >= self.frontier_floor:
            return "frontier"
        return "mid"

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Average the 3 LightGBM regressors and clip to the training range."""
        preds = [np.clip(m.predict(features), 0, 10) for m in self.models]
        return np.clip(np.mean(preds, axis=0), 0, 10)


def _validate(bundle: dict, policy_id: str) -> None:
    """Fail loudly on drift rather than mis-scoring live traffic."""
    n_features = bundle.get("feature_count")
    if n_features != FEATURE_COUNT:
        raise ValueError(
            f"{policy_id}: artifact has {n_features} features, builder produces {FEATURE_COUNT}. "
            "The artifact and the feature builder have drifted."
        )
    if bundle.get("feature_order") != FEATURE_ORDER:
        raise ValueError(
            f"{policy_id}: manifest feature_order is {bundle.get('feature_order')!r}, "
            f"expected {FEATURE_ORDER!r}"
        )
    domain_order = tuple(bundle.get("domain_order") or ())
    if domain_order != DOMAIN_ORDER:
        raise ValueError(
            f"{policy_id}: manifest domain_order is {domain_order}, expected {DOMAIN_ORDER}"
        )
    rule = bundle.get("tier_rule")
    if rule not in VALID_RULES:
        raise ValueError(
            f"{policy_id}: missing or unknown tier_rule {rule!r}; "
            "refusing to guess the tier rule from n_tiers"
        )
    if rule == TIER2 and bundle.get("n_tiers") != 2:
        raise ValueError(f"{policy_id}: tier_rule {rule} contradicts n_tiers {bundle.get('n_tiers')}")
    if rule == TIER3 and bundle.get("n_tiers") != 3:
        raise ValueError(f"{policy_id}: tier_rule {rule} contradicts n_tiers {bundle.get('n_tiers')}")
    thr = bundle.get("thr") or {}
    if "cheap_ceil" not in thr:
        raise ValueError(f"{policy_id}: manifest thr is missing cheap_ceil")
    if rule == TIER3 and "frontier_floor" not in thr:
        raise ValueError(f"{policy_id}: 3-tier manifest thr is missing frontier_floor")


def load_policy(policy_id: str = DEFAULT_POLICY) -> Policy:
    """Load and validate a support policy bundle. Raises on unknown ids."""
    if policy_id not in POLICY_FILES:
        raise ValueError(f"unknown support policy {policy_id!r}; expected one of {VALID_POLICIES}")
    path = MODELS_DIR / POLICY_FILES[policy_id]
    if not path.is_file():
        raise FileNotFoundError(f"support policy artifact not found: {path}")
    bundle = joblib.load(path)
    _validate(bundle, policy_id)
    thr = bundle["thr"]
    return Policy(
        id=policy_id,
        n_tiers=int(bundle["n_tiers"]),
        tier_rule=str(bundle["tier_rule"]),
        cheap_ceil=float(thr["cheap_ceil"]),
        frontier_floor=float(thr.get("frontier_floor", thr["cheap_ceil"])),
        models=tuple(bundle["models"]),
        feature_count=int(bundle["feature_count"]),
        domain_order=tuple(bundle["domain_order"]),
        honest_eval=dict(bundle.get("honest_eval") or {}),
    )


def policy_manifest() -> list[dict]:
    """Frontend-facing description of each available policy."""
    out = []
    for pid in POLICY_FILES:
        try:
            p = load_policy(pid)
        except Exception as exc:  # pragma: no cover - surfaced to the UI as unavailable
            out.append({"id": pid, "available": False, "error": str(exc)})
            continue
        ev = p.honest_eval
        out.append(
            {
                "id": pid,
                "available": True,
                "n_tiers": p.n_tiers,
                "tiers": list(p.tiers),
                "tier_rule": p.tier_rule,
                "cheap_ceil": p.cheap_ceil,
                "frontier_floor": p.frontier_floor,
                "mae_mean": ev.get("mae_mean"),
                "mae_worst": ev.get("mae_worst"),
                "recall_cheap": ev.get("recall_cheap"),
                "recall_frontier": ev.get("recall_frontier"),
                "traffic": ev.get("traffic"),
            }
        )
    return out
