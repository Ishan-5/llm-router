import logging
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
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
            session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).filter(*base_filter).group_by(RequestLog.tier).all()
            if tier and avg is not None
        }
        daily_actual = session.query(func.date(RequestLog.created_at).label("day"), func.sum(RequestLog.cost_usd)).filter(*base_filter).group_by("day").order_by("day").all()
        daily_costs = [
            {"date": str(day), "actual_cost": float(actual or 0), "hypothetical_cost": hyp_by_day.get(str(day), 0.0)}
            for day, actual in daily_actual
        ]
        cache_savings_usd = float(session.query(func.sum(RequestLog.tokens_saved_usd)).filter(RequestLog.cache_hit == True, *base_filter).scalar() or 0.0)
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)
        average_quality = float(session.query(func.avg(RequestLog.quality_score)).filter(*base_filter, RequestLog.quality_score.isnot(None)).scalar() or 0.0)
        quality_judged_count = session.query(func.count(RequestLog.id)).filter(*base_filter, RequestLog.quality_judged == True).scalar() or 0
        judged_quality_avg = float(session.query(func.avg(RequestLog.quality_score)).filter(*base_filter, RequestLog.quality_judged == True).scalar() or 0.0)
        feedback_counts = dict(session.query(RequestLog.feedback, func.count(RequestLog.id)).filter(*base_filter, RequestLog.feedback.in_(("up", "down"))).group_by(RequestLog.feedback).all())
        feedback_total = int(feedback_counts.get("up", 0) + feedback_counts.get("down", 0))

        return {
            "total_requests": total_requests, "tier_counts": tier_counts, "tier_costs": tier_costs,
            "total_actual_cost": total_actual_cost, "total_hypothetical_cost": total_hypothetical_cost,
            "cache_hit_rate": cache_hit_rate, "fallback_count": fallback_count,
            "avg_latency_by_tier": avg_latency_by_tier, "daily_costs": daily_costs,
            "cache_savings_usd": cache_savings_usd, "routing_savings_usd": routing_savings_usd,
            "total_savings_usd": total_savings_usd, "average_quality": round(average_quality, 4),
            "quality_judged_count": quality_judged_count, "judged_quality_avg": round(judged_quality_avg, 4),
            "feedback_counts": {"up": int(feedback_counts.get("up", 0)), "down": int(feedback_counts.get("down", 0))},
            "feedback_total": feedback_total,
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


class EvaluateRequest(BaseModel):
    queries: list[str]


@router.post("/evaluate")
def evaluate(req: EvaluateRequest):
    from predict_difficulty import predict_difficulty
    margins = [("economy", 0.0), ("balanced", 1.0), ("quality", 2.0)]
    results = []
    for q in req.queries:
        score = predict_difficulty(q)
        entry = {"query": q, "difficulty_score": round(score, 4)}
        for mode_name, margin in margins:
            entry[f"tier_{mode_name}"] = score_to_tier(score, margin=margin)[0]
        results.append(entry)
    thresholds = [
        {"mode": "economy",  "cheap_below": 3.475, "frontier_above": 4.9},
        {"mode": "balanced", "cheap_below": 3.4,   "frontier_above": 4.6},
        {"mode": "quality",  "cheap_below": 3.325, "frontier_above": 4.3},
    ]
    return {"results": results, "thresholds": thresholds}
