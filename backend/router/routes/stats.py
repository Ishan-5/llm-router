import logging
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from router.db import SessionLocal, RequestLog, ApiKey
from router.auth import require_api_key, require_any_auth
from router.config import MODEL_CONFIG
from router.auth import is_admin_user_id
from predict_difficulty import score_to_tier

router = APIRouter()
log = logging.getLogger("routewise")


@router.get("/logs")
def get_logs(limit: int = 50, api_key: ApiKey = Depends(require_api_key)):
    limit = max(1, min(limit, 100))
    session = SessionLocal()
    try:
        rows = (
            session.query(RequestLog)
            .filter(RequestLog.api_key_id == api_key.id)
            .order_by(RequestLog.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id, "query": r.query,
                "response": (r.response[:500] + "...") if r.response and len(r.response) > 500 else r.response,
                "tier": r.tier, "intended_tier": r.intended_tier, "model_id": r.model_id,
                "difficulty_score": r.difficulty_score, "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens, "cost_usd": r.cost_usd, "latency_ms": r.latency_ms,
                "cache_hit": r.cache_hit, "cache_similarity": r.cache_similarity,
                "fallback_used": r.fallback_used, "tokens_saved_usd": r.tokens_saved_usd,
                "llm_difficulty_score": r.llm_difficulty_score, "llm_predicted_tier": r.llm_predicted_tier,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@router.get("/logs/{log_id}")
def get_log_detail(log_id: int, api_key: ApiKey = Depends(require_api_key)):
    session = SessionLocal()
    try:
        r = session.query(RequestLog).filter(RequestLog.id == log_id, RequestLog.api_key_id == api_key.id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Log entry not found")
        return {
            "id": r.id, "query": r.query, "response": r.response,
            "tier": r.tier, "intended_tier": r.intended_tier, "model_id": r.model_id,
            "difficulty_score": r.difficulty_score, "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens, "cost_usd": r.cost_usd, "latency_ms": r.latency_ms,
            "cache_hit": r.cache_hit, "cache_similarity": r.cache_similarity,
            "fallback_used": r.fallback_used, "tokens_saved_usd": r.tokens_saved_usd,
            "llm_difficulty_score": r.llm_difficulty_score, "llm_predicted_tier": r.llm_predicted_tier,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
    finally:
        session.close()


@router.get("/stats")
def get_stats(api_key: ApiKey = Depends(require_api_key)):
    session = SessionLocal()
    try:
        is_admin = is_admin_user_id(api_key.user_id)
        base_filter = [] if is_admin else [RequestLog.api_key_id == api_key.id]

        total_requests = session.query(func.count(RequestLog.id)).filter(*base_filter).scalar() or 0
        tier_counts = dict(session.query(RequestLog.tier, func.count(RequestLog.id)).filter(*base_filter).group_by(RequestLog.tier).all())
        tier_costs = {
            tier: float(cost or 0.0)
            for tier, cost in session.query(RequestLog.tier, func.sum(RequestLog.cost_usd)).filter(*base_filter).group_by(RequestLog.tier).all()
            if tier
        }
        total_actual_cost = float(session.query(func.sum(RequestLog.cost_usd)).filter(*base_filter).scalar() or 0.0)
        cache_hits = session.query(func.count(RequestLog.id)).filter(RequestLog.cache_hit == True, *base_filter).scalar() or 0
        cache_hit_rate = (cache_hits / total_requests) if total_requests else 0.0
        fallback_count = session.query(func.count(RequestLog.id)).filter(RequestLog.fallback_used == True, *base_filter).scalar() or 0

        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).filter(*base_filter).all()

        total_hypothetical_cost = 0.0
        hyp_by_day = defaultdict(float)
        for in_tok, out_tok, created_at in token_rows:
            hyp_cost = (
                (in_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_input"]
                + (out_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_output"]
            )
            total_hypothetical_cost += hyp_cost
            day = created_at.date().isoformat() if created_at else "unknown"
            hyp_by_day[day] += hyp_cost

        avg_latency_by_tier = {
            tier: float(avg) for tier, avg in
            session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).filter(
                *base_filter, RequestLog.cache_hit == False,
            ).group_by(RequestLog.tier).all()
            if tier and avg is not None
        }
        # Cache hits are excluded above. routes/route.py logs a hit against the
        # tier it WOULD have served from, with the near-instant lookup time, so
        # including them silently compared "model call + cache lookup" against
        # "model call" and made the chart unreadable as a tier comparison.
        # avg_latency_ms below stays request-weighted across everything served,
        # which is the number a user actually waits for.
        #
        # These figures are wall-clock provider time, not model capability: they
        # are dominated by provider queueing and 429 backoff. Groq's LPUs in
        # particular make the cheap tier look slower than the frontier tier, which
        # says nothing about answer quality and should not be read as if it did.
        cache_hit_latency_ms = float(
            session.query(func.avg(RequestLog.latency_ms)).filter(
                *base_filter, RequestLog.cache_hit == True,
            ).scalar() or 0.0
        )
        # Request-weighted mean across every logged request. Averaging the per-tier
        # means instead would over-weight a tier with only a handful of requests.
        avg_latency_ms = float(session.query(func.avg(RequestLog.latency_ms)).filter(*base_filter).scalar() or 0.0)
        daily_actual = session.query(func.date(RequestLog.created_at).label("day"), func.sum(RequestLog.cost_usd)).filter(*base_filter).group_by("day").order_by("day").all()
        daily_costs = [
            {"date": str(day), "actual_cost": float(actual or 0), "hypothetical_cost": hyp_by_day.get(str(day), 0.0)}
            for day, actual in daily_actual
        ]
        cache_savings_usd = float(session.query(func.sum(RequestLog.tokens_saved_usd)).filter(RequestLog.cache_hit == True, *base_filter).scalar() or 0.0)
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)
        # Cache hits log 0 tokens and $0, so they contribute nothing to either
        # hypothetical or actual cost. The two savings components are therefore
        # disjoint, and the percentage is taken against hypothetical + cache
        # savings so it agrees with total_savings_usd above.
        savings_baseline = total_hypothetical_cost + cache_savings_usd
        savings_pct = round((1 - total_actual_cost / savings_baseline) * 100, 1) if savings_baseline > 0 else 0.0
        # A fallback is a *successful* answer served by another tier, so it must not
        # count against success. AllTiersFailedError rows are logged as tier
        # "failed" (see routes/route.py), which is the real failure signal.
        failed_count = session.query(func.count(RequestLog.id)).filter(RequestLog.tier == "failed", *base_filter).scalar() or 0
        success_rate_pct = round((total_requests - failed_count) / total_requests * 100, 1) if total_requests else 100.0
        quality_judged_count = session.query(func.count(RequestLog.id)).filter(*base_filter, RequestLog.quality_judged == True).scalar() or 0
        judged_quality_avg = float(session.query(func.avg(RequestLog.quality_score)).filter(*base_filter, RequestLog.quality_judged == True).scalar() or 0.0)
        feedback_counts = dict(session.query(RequestLog.feedback, func.count(RequestLog.id)).filter(*base_filter, RequestLog.feedback.in_(("up", "down"))).group_by(RequestLog.feedback).all())
        feedback_total = int(feedback_counts.get("up", 0) + feedback_counts.get("down", 0))

        label_rows = session.query(RequestLog.difficulty_score, RequestLog.llm_difficulty_score).filter(
            *base_filter, RequestLog.llm_difficulty_score.isnot(None),
            RequestLog.difficulty_score.isnot(None),
            RequestLog.cache_hit == False, RequestLog.tier != "web",
        ).all()
        tier_rank = {"cheap": 0, "mid": 1, "frontier": 2}
        labeled_count = len(label_rows)
        agree = under_routed = over_routed = 0
        score_diffs = []
        for ml_score, llm_score in label_rows:
            ml_tier = score_to_tier(ml_score, margin=1.0)[0]
            llm_tier = score_to_tier(llm_score, margin=1.0)[0]
            score_diffs.append(abs(ml_score - llm_score))
            if ml_tier == llm_tier:
                agree += 1
            elif tier_rank.get(ml_tier, 1) < tier_rank.get(llm_tier, 1):
                under_routed += 1  # ML routed cheaper than the LLM says it should have
            else:
                over_routed += 1  # ML routed more expensively than needed
        labeling = {
            "labeled_count": labeled_count,
            "agreement_pct": round(agree / labeled_count * 100, 1) if labeled_count else None,
            "under_routed": under_routed,
            "over_routed": over_routed,
            "under_routed_pct": round(under_routed / labeled_count * 100, 1) if labeled_count else None,
            "over_routed_pct": round(over_routed / labeled_count * 100, 1) if labeled_count else None,
            "mae": round(sum(score_diffs) / len(score_diffs), 4) if score_diffs else None,
        }

        return {
            "total_requests": total_requests, "tier_counts": tier_counts, "tier_costs": tier_costs,
            "total_actual_cost": total_actual_cost, "total_hypothetical_cost": total_hypothetical_cost,
            "cache_hit_rate": cache_hit_rate, "fallback_count": fallback_count,
            "failed_count": failed_count, "success_rate_pct": success_rate_pct,
            "avg_latency_by_tier": avg_latency_by_tier, "avg_latency_ms": round(avg_latency_ms, 1),
        "cache_hit_latency_ms": round(cache_hit_latency_ms, 1),
            "daily_costs": daily_costs,
            "cache_savings_usd": cache_savings_usd, "routing_savings_usd": routing_savings_usd,
            "total_savings_usd": total_savings_usd, "savings_pct": savings_pct,
            "quality_judged_count": quality_judged_count, "judged_quality_avg": round(judged_quality_avg, 4),
            "feedback_counts": {"up": int(feedback_counts.get("up", 0)), "down": int(feedback_counts.get("down", 0))},
            "feedback_total": feedback_total,
            "labeling": labeling,
            "is_global": is_admin,
        }
    finally:
        session.close()


@router.get("/analytics")
def get_analytics(api_key: ApiKey = Depends(require_api_key)):
    session = SessionLocal()
    try:
        base_filter = [RequestLog.api_key_id == api_key.id]
        total_requests = session.query(func.count(RequestLog.id)).filter(*base_filter).scalar() or 0
        tier_costs = dict(session.query(RequestLog.tier, func.sum(RequestLog.cost_usd)).filter(*base_filter).group_by(RequestLog.tier).all())
        model_costs = dict(session.query(RequestLog.model_id, func.sum(RequestLog.cost_usd)).filter(*base_filter).group_by(RequestLog.model_id).all())
        tier_tokens = {}
        for tier, in_tok, out_tok in session.query(RequestLog.tier, func.sum(RequestLog.input_tokens), func.sum(RequestLog.output_tokens)).filter(*base_filter).group_by(RequestLog.tier).all():
            tier_tokens[tier] = {"input": in_tok or 0, "output": out_tok or 0}
        daily_rows = session.query(func.date(RequestLog.created_at).label("day"), func.sum(RequestLog.cost_usd), func.count(RequestLog.id), func.avg(RequestLog.latency_ms)).filter(*base_filter).group_by("day").order_by(func.date(RequestLog.created_at).desc()).limit(30).all()
        daily = [{"date": str(day), "cost": float(cost or 0), "requests": count, "avg_latency": round(float(avg or 0), 1)} for day, cost, count, avg in reversed(daily_rows)]
        cache_hits = session.query(func.count(RequestLog.id)).filter(*base_filter, RequestLog.cache_hit == True).scalar() or 0
        cache_savings = float(session.query(func.sum(RequestLog.tokens_saved_usd)).filter(*base_filter, RequestLog.cache_hit == True).scalar() or 0.0)
        fallbacks = session.query(func.count(RequestLog.id)).filter(*base_filter, RequestLog.fallback_used == True).scalar() or 0
        latency_by_tier = dict(session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).filter(*base_filter).group_by(RequestLog.tier).all())
        top_expensive = session.query(RequestLog.id, RequestLog.query, RequestLog.tier, RequestLog.model_id, RequestLog.cost_usd, RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).filter(*base_filter).order_by(RequestLog.cost_usd.desc()).limit(5).all()
        top_expensive_list = [{"id": r.id, "query": r.query[:100] + "..." if r.query and len(r.query) > 100 else r.query, "tier": r.tier, "model": r.model_id, "cost": float(r.cost_usd or 0), "tokens": (r.input_tokens or 0) + (r.output_tokens or 0), "created_at": r.created_at.isoformat() if r.created_at else None} for r in top_expensive]
        total_cost = float(session.query(func.sum(RequestLog.cost_usd)).filter(*base_filter).scalar() or 0.0)
        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens).filter(*base_filter).all()
        hypothetical = sum((in_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_input"] + (out_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_output"] for in_tok, out_tok in token_rows)
        return {
            "summary": {
                "total_requests": total_requests, "total_cost": round(total_cost, 6),
                "hypothetical_cost": round(hypothetical, 6), "savings": round(max(0, hypothetical - total_cost), 6),
                "savings_pct": round((1 - total_cost / hypothetical) * 100, 1) if hypothetical > 0 else 0,
                "cache_hit_rate": round(cache_hits / total_requests * 100, 1) if total_requests else 0,
                "cache_savings": round(cache_savings, 6),
                "fallback_rate": round(fallbacks / total_requests * 100, 1) if total_requests else 0,
            },
            "tier_costs": {k: round(float(v or 0), 6) for k, v in tier_costs.items()},
            "model_costs": {k: round(float(v or 0), 6) for k, v in model_costs.items()},
            "tier_tokens": tier_tokens, "daily": daily,
            "latency_by_tier": {k: round(float(v or 0), 1) for k, v in latency_by_tier.items()},
            "top_expensive": top_expensive_list,
        }
    finally:
        session.close()


@router.get("/calibrate")
def calibrate(auth=Depends(require_any_auth)):
    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            base_filter = [RequestLog.api_key_id == auth["record"].id, RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        else:
            key_ids = [k.id for k in session.query(ApiKey.id).filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True).all()]
            if not key_ids:
                return {"message": "No API keys found. Create one in Settings first.", "modes": []}
            base_filter = [RequestLog.api_key_id.in_(key_ids), RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        rows = session.query(RequestLog.difficulty_score, RequestLog.input_tokens, RequestLog.output_tokens).filter(*base_filter).order_by(RequestLog.created_at.desc()).limit(200).all()
        if not rows:
            return {"message": "Not enough data yet. Send some routed requests first.", "recommendation": None}

        margins = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
        results = []
        for mode_name, margin in margins:
            cheap_count = mid_count = frontier_count = 0
            total_cost = 0.0
            for score, in_tok, out_tok in rows:
                tier, _, _ = score_to_tier(score, margin=margin)
                if tier == "frontier":
                    frontier_count += 1
                    tier_prices = MODEL_CONFIG["frontier"]
                elif tier == "cheap":
                    cheap_count += 1
                    tier_prices = MODEL_CONFIG["cheap"]
                else:
                    mid_count += 1
                    tier_prices = MODEL_CONFIG["mid"]
                total_cost += (in_tok or 0) / 1_000_000 * tier_prices["price_per_m_input"]
                total_cost += (out_tok or 0) / 1_000_000 * tier_prices["price_per_m_output"]
            frontier_cost = sum((in_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_input"] + (out_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_output"] for _, in_tok, out_tok in rows)
            savings_pct = round((1 - total_cost / frontier_cost) * 100, 1) if frontier_cost > 0 else 0
            results.append({"mode": mode_name, "margin": margin, "cheap_pct": round(cheap_count / len(rows) * 100, 1), "mid_pct": round(mid_count / len(rows) * 100, 1), "frontier_pct": round(frontier_count / len(rows) * 100, 1), "estimated_cost": round(total_cost, 6), "savings_pct": savings_pct})
        return {"analyzed_requests": len(rows), "modes": results}
    finally:
        session.close()


@router.get("/compare")
def compare(auth=Depends(require_any_auth)):
    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            base_filter = [RequestLog.api_key_id == auth["record"].id, RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        else:
            key_ids = [k.id for k in session.query(ApiKey.id).filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True).all()]
            if not key_ids:
                return {"message": "No API keys found.", "modes": []}
            base_filter = [RequestLog.api_key_id.in_(key_ids), RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        rows = session.query(RequestLog.difficulty_score, RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).filter(*base_filter).order_by(RequestLog.created_at.desc()).limit(500).all()
        if not rows:
            return {"message": "Not enough data.", "modes": []}

        ranges = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
        results = []
        for mode_name, margin in ranges:
            total_cost = 0.0
            for score, in_tok, out_tok, _ in rows:
                tier, _, _ = score_to_tier(score, margin=margin)
                tier_prices = MODEL_CONFIG["frontier"] if tier == "frontier" else MODEL_CONFIG["cheap"] if tier == "cheap" else MODEL_CONFIG["mid"]
                total_cost += (in_tok or 0) / 1_000_000 * tier_prices["price_per_m_input"]
                total_cost += (out_tok or 0) / 1_000_000 * tier_prices["price_per_m_output"]
            baseline_cost = sum((in_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_input"] + (out_tok or 0) / 1_000_000 * MODEL_CONFIG["frontier"]["price_per_m_output"] for _, in_tok, out_tok, _ in rows)
            savings_vs_frontier = round((1 - total_cost / baseline_cost) * 100, 1) if baseline_cost > 0 else 0
            results.append({"mode": mode_name, "margin": margin, "estimated_cost": round(total_cost, 6), "frontier_baseline_cost": round(baseline_cost, 6), "savings_pct": savings_vs_frontier})
        return {"analyzed_requests": len(rows), "modes": results}
    finally:
        session.close()


# Honest eval numbers for the generic (emma) model. These live in MODEL_SPEC.md
# as prose, not in a loadable artifact, so they are pinned here rather than
# pretending lisa/kate's train-on-17,600-tickets numbers are comparable -- they
# are measured on a different holdout (783 Claude-gold general rows).
GENERIC_EVAL = {
    "mae": 1.018,
    "spearman": 0.861,
    "exact_acc_pct": 77.5,
    "recall_frontier_pct": 58.0,
    "cheap_precision_pct": 94.0,
    "holdout_rows": 783,
    "source": "MODEL_SPEC.md — 783 held-out Claude-gold general rows, balanced thresholds (cheap ≤ 4.5 / frontier ≥ 6.0)",
}


@router.get("/policy-analytics")
def policy_analytics(auth=Depends(require_any_auth)):
    """Per-policy cost & frontier-escape comparison over real logged traffic.

    request_logs has no support_mode column, so this is a replay estimate: the
    stored difficulty_score of each non-cache, non-web request is handed to each
    policy's own tier rule under today's pricing. It answers "what would my last
    500 requests have cost under emma vs lisa vs kate, and how much traffic
    would each have sent to the frontier?" -- the same trick /compare and
    /calibrate use for the three sliders.
    """
    import feature_builder as _fb  # same path dance route.py uses

    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            base_filter = [RequestLog.api_key_id == auth["record"].id, RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        else:
            key_ids = [k.id for k in session.query(ApiKey.id).filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True).all()]
            if not key_ids:
                return {"message": "No API keys found.", "analyzed_requests": 0, "models": []}
            base_filter = [RequestLog.api_key_id.in_(key_ids), RequestLog.cache_hit == False, RequestLog.tier != "web", RequestLog.difficulty_score.isnot(None)]
        rows = session.query(RequestLog.difficulty_score, RequestLog.input_tokens, RequestLog.output_tokens).filter(*base_filter).order_by(RequestLog.created_at.desc()).limit(500).all()
        if not rows:
            return {"message": "Not enough data yet. Send some routed requests first.", "analyzed_requests": 0, "models": []}

        def _cost(tier, in_tok, out_tok):
            prices = MODEL_CONFIG["frontier"] if tier == "frontier" else MODEL_CONFIG["cheap"] if tier == "cheap" else MODEL_CONFIG["mid"]
            return (in_tok or 0) / 1_000_000 * prices["price_per_m_input"] + (out_tok or 0) / 1_000_000 * prices["price_per_m_output"]

        # (product id, support_mode, generic margin for emma only)
        specs = [
            ("emma", "generic", None),
            ("lisa", "3tier", None),
            ("kate", "2tier", None),
        ]
        policies = {}
        for pid in ("3tier", "2tier"):
            try:
                policies[pid] = _fb.load_policy(pid)
            except Exception:
                policies[pid] = None

        frontier_baseline = sum(_cost("frontier", in_tok, out_tok) for _, in_tok, out_tok in rows)
        models = []
        for model_id, support_mode, _margin in specs:
            policy = None if support_mode == "generic" else policies.get(support_mode)
            if support_mode != "generic" and policy is None:
                models.append({"id": model_id, "support_mode": support_mode, "available": False})
                continue

            counts = {"cheap": 0, "mid": 0, "frontier": 0}
            cost = 0.0
            for score, in_tok, out_tok in rows:
                if support_mode == "generic":
                    tier = score_to_tier(score, margin=1.0)[0]
                else:
                    tier = policy.tier_for(score)
                counts[tier] = counts.get(tier, 0) + 1
                cost += _cost(tier, in_tok, out_tok)

            n = len(rows)
            traffic = {t: round(cnt / n, 4) for t, cnt in counts.items() if cnt}
            saved = round((1 - cost / frontier_baseline) * 100, 1) if frontier_baseline > 0 else 0.0

            if support_mode == "generic":
                _, cheap_ceil, frontier_floor = score_to_tier(0.0, margin=1.0)
                cuts = {"cheap": round(cheap_ceil, 1), "frontier": round(frontier_floor, 1)}
                tiers = ["cheap", "mid", "frontier"]
                eval_block = dict(GENERIC_EVAL)
            else:
                ev = policy.honest_eval
                cuts = {"cheap": round(policy.cheap_ceil, 1), "frontier": round(policy.frontier_floor, 1)}
                tiers = list(policy.tiers)
                recall_frontier = ev.get("recall_frontier")
                eval_block = {
                    "mae": ev.get("mae_mean"),
                    "mae_worst": ev.get("mae_worst"),
                    "spearman": ev.get("spearman_mean"),
                    "recall_frontier_pct": round(recall_frontier * 100, 1) if recall_frontier is not None else None,
                    # Escape rate = complement of frontier recall: the share of
                    # gold-frontier requests the policy would have let slip.
                    "frontier_escape_pct": round((1 - recall_frontier) * 100, 1) if recall_frontier is not None else None,
                    "traffic": ev.get("traffic"),
                    "source": f"{policy.n_tiers}-tier policy on 17,600 labeled support tickets, mean of 3 batch-level splits",
                }

            models.append(
                {
                    "id": model_id,
                    "support_mode": support_mode,
                    "available": True,
                    "tiers": tiers,
                    "cuts": cuts,
                    "traffic": traffic,
                    "counts": counts,
                    "cost_usd": round(cost, 6),
                    "cost_per_request": round(cost / n, 6),
                    "frontier_baseline_cost_usd": round(frontier_baseline, 6),
                    "savings_pct": saved,
                    "eval": eval_block,
                }
            )

        return {
            "analyzed_requests": n,
            "is_estimate": True,
            "caveat": (
                f"Replayed your last {n} routed requests (cache hits and web answers excluded) through each policy "
                "under today's pricing. The offline eval numbers use each model's own holdout, so they are directional, "
                "not apples-to-apples."
            ),
            "frontier_baseline_cost_usd": round(frontier_baseline, 6),
            "models": models,
        }
    finally:
        session.close()


class EvaluateRequest(BaseModel):
    # Each query costs a real embedding plus a forward pass, and this route is
    # unauthenticated, so an unbounded list would be a free compute endpoint.
    queries: list[str] = Field(..., max_length=50)


@router.post("/evaluate")
def evaluate(req: EvaluateRequest):
    from predict_difficulty import predict_difficulty, score_to_tier
    from router.support_policy import get_tier_with_mode
    margins = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
    support_modes = [("emma", None), ("lisa", "3tier"), ("kate", "2tier")]
    results = []
    for q in req.queries:
        score = predict_difficulty(q)
        entry = {"query": q, "difficulty_score": round(score, 4)}
        for mode_name, margin in margins:
            entry[f"tier_{mode_name}"] = score_to_tier(score, margin=margin)[0]
        for model_name, support_mode in support_modes:
            mode = support_mode or "generic"
            try:
                tier = get_tier_with_mode(q, margin=1.0, support_mode=support_mode or "generic")[1]
                entry[f"mode_{mode}"] = tier
            except Exception:
                entry[f"mode_{mode}"] = "unavailable"
        results.append(entry)
    thresholds = [
        {
            "mode": mode_name,
            "cheap_below": score_to_tier(0.0, margin=margin)[1],
            "frontier_above": score_to_tier(0.0, margin=margin)[2],
        }
        for mode_name, margin in margins
    ]
    return {"results": results, "thresholds": thresholds}


# --- Difficulty calibration --------------------------------------------------
#
# Routing turns one number into a price, so that number has to mean something.
# This endpoint answers "when the classifier says 6/10, how hard was the query
# really?" by comparing the predicted score against the independent
# LLM-as-labeler score (llm_difficulty_score) written for a sample of requests,
# and reports how each tier actually performed once it was chosen.
#
# Read-only: it never scores new text and never calls a provider.

_CALIBRATION_BINS = 10  # one bin per point of the 0-10 difficulty scale


@router.get("/stats/reliability")
def reliability(auth=Depends(require_any_auth)):
    session = SessionLocal()
    try:
        if auth["type"] == "api_key" and auth["record"]:
            scope = [RequestLog.api_key_id == auth["record"].id]
        else:
            key_ids = [
                k.id
                for k in session.query(ApiKey.id)
                .filter(ApiKey.user_id == auth["user_id"], ApiKey.is_active == True)
                .all()
            ]
            if not key_ids:
                return {
                    "message": "No API keys found. Create one in Settings first.",
                    "sample": {"total": 0, "scored": 0, "labeled": 0, "judged": 0, "with_feedback": 0},
                }
            scope = [RequestLog.api_key_id.in_(key_ids)]

        rows = (
            session.query(
                RequestLog.difficulty_score,
                RequestLog.llm_difficulty_score,
                RequestLog.intended_tier,
                RequestLog.tier,
                RequestLog.fallback_used,
                RequestLog.cost_usd,
                RequestLog.latency_ms,
                RequestLog.quality_score,
                RequestLog.quality_judged,
                RequestLog.feedback,
            )
            .filter(*scope, RequestLog.cache_hit == False, RequestLog.tier != "web")
            .order_by(RequestLog.created_at.desc())
            .limit(2000)
            .all()
        )

        if not rows:
            return {
                "message": "No routed requests yet. Send a few questions first.",
                "sample": {"total": 0, "scored": 0, "labeled": 0, "judged": 0, "with_feedback": 0},
            }

        _, cheap_ceil, frontier_floor = score_to_tier(0.0, margin=1.0)

        bins = [{"pred": 0.0, "actual": 0.0, "n": 0} for _ in range(_CALIBRATION_BINS)]
        histogram = [0] * _CALIBRATION_BINS
        abs_errors = []
        scored = labeled = judged = with_feedback = borderline = 0
        tiers: dict[str, dict] = {}
        confusion: dict[tuple, int] = {}

        def _bin(value):
            return max(0, min(_CALIBRATION_BINS - 1, int(value)))

        for row in rows:
            (pred, label, intended, served, fell_back, cost,
             latency, quality, is_judged, feedback) = row

            if pred is not None:
                scored += 1
                histogram[_bin(pred)] += 1
                if abs(pred - cheap_ceil) <= 0.25 or abs(pred - frontier_floor) <= 0.25:
                    borderline += 1

            if pred is not None and label is not None:
                labeled += 1
                slot = bins[_bin(pred)]
                slot["pred"] += pred
                slot["actual"] += label
                slot["n"] += 1
                abs_errors.append(abs(pred - label))

            if is_judged and quality is not None:
                judged += 1
            if feedback:
                with_feedback += 1

            name = served or "unknown"
            tier = tiers.setdefault(
                name,
                {
                    "tier": name, "n": 0, "cost": 0.0, "latency": 0.0, "fallbacks": 0,
                    "quality_sum": 0.0, "quality_n": 0, "up": 0, "down": 0,
                },
            )
            tier["n"] += 1
            tier["cost"] += cost or 0.0
            tier["latency"] += latency or 0.0
            if fell_back:
                tier["fallbacks"] += 1
            if is_judged and quality is not None:
                tier["quality_sum"] += quality
                tier["quality_n"] += 1
            if feedback == "up":
                tier["up"] += 1
            elif feedback == "down":
                tier["down"] += 1

            if intended and served:
                confusion[(intended, served)] = confusion.get((intended, served), 0) + 1

        calibration = []
        ece = 0.0
        for i, slot in enumerate(bins):
            if not slot["n"]:
                continue
            mean_pred = slot["pred"] / slot["n"]
            mean_actual = slot["actual"] / slot["n"]
            calibration.append(
                {
                    "bin": f"{i}-{i + 1}",
                    "predicted": round(mean_pred, 2),
                    "actual": round(mean_actual, 2),
                    "n": slot["n"],
                }
            )
            # Expected calibration error: weight each bin by how much of the
            # labelled sample it holds, so it is comparable across runs.
            if labeled:
                ece += (slot["n"] / labeled) * abs(mean_actual - mean_pred)

        tier_rows = [
            {
                "tier": t["tier"],
                "requests": t["n"],
                "avg_cost": round(t["cost"] / t["n"], 6),
                "avg_latency_ms": round(t["latency"] / t["n"], 0),
                "fallback_rate": round(t["fallbacks"] / t["n"], 3),
                "avg_quality": round(t["quality_sum"] / t["quality_n"], 2) if t["quality_n"] else None,
                "feedback_up": t["up"],
                "feedback_down": t["down"],
            }
            for t in sorted(tiers.values(), key=lambda x: x["n"], reverse=True)
        ]

        return {
            "sample": {
                "total": len(rows),
                "scored": scored,
                "labeled": labeled,
                "judged": judged,
                "with_feedback": with_feedback,
            },
            "thresholds": {"cheap_ceil": cheap_ceil, "frontier_floor": frontier_floor},
            "mae": round(sum(abs_errors) / len(abs_errors), 3) if abs_errors else None,
            "ece": round(ece, 3) if labeled else None,
            "borderline_share": round(borderline / scored, 3) if scored else None,
            "reliability": calibration,
            "histogram": [{"score": i, "count": c} for i, c in enumerate(histogram)],
            "tiers": tier_rows,
            "confusion": [
                {"intended": pair[0], "served": pair[1], "requests": n}
                for pair, n in sorted(confusion.items(), key=lambda kv: kv[1], reverse=True)
            ],
        }
    finally:
        session.close()
