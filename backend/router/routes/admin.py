import logging
from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy import func
from router.db import SessionLocal, RequestLog, ApiKey
from router.auth import require_admin_any
from router.config import MODEL_CONFIG

router = APIRouter()
log = logging.getLogger("routewise")


@router.get("/admin/stats")
def admin_stats(user_id: str = Depends(require_admin_any)):
    session = SessionLocal()
    try:
        total_requests = session.query(func.count(RequestLog.id)).scalar() or 0
        tier_counts = dict(session.query(RequestLog.tier, func.count(RequestLog.id)).group_by(RequestLog.tier).all())
        tier_costs = {tier: float(cost or 0.0) for tier, cost in session.query(RequestLog.tier, func.sum(RequestLog.cost_usd)).group_by(RequestLog.tier).all() if tier}
        total_actual_cost = float(session.query(func.sum(RequestLog.cost_usd)).scalar() or 0.0)
        cache_hits = session.query(func.count(RequestLog.id)).filter(RequestLog.cache_hit == True).scalar() or 0
        cache_hit_rate = (cache_hits / total_requests) if total_requests else 0.0
        fallback_count = session.query(func.count(RequestLog.id)).filter(RequestLog.fallback_used == True).scalar() or 0

        frontier_cfg = MODEL_CONFIG["frontier"]
        token_rows = session.query(RequestLog.input_tokens, RequestLog.output_tokens, RequestLog.created_at).all()
        total_hypothetical_cost = 0.0
        hyp_by_day = defaultdict(float)
        for in_tok, out_tok, created_at in token_rows:
            hyp_cost = (in_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_input"] + (out_tok or 0) / 1_000_000 * frontier_cfg["price_per_m_output"]
            total_hypothetical_cost += hyp_cost
            day = created_at.date().isoformat() if created_at else "unknown"
            hyp_by_day[day] += hyp_cost

        avg_latency_by_tier = {tier: float(avg) for tier, avg in session.query(RequestLog.tier, func.avg(RequestLog.latency_ms)).group_by(RequestLog.tier).all() if tier and avg is not None}
        daily_actual = session.query(func.date(RequestLog.created_at).label("day"), func.sum(RequestLog.cost_usd)).group_by("day").order_by("day").all()
        daily_costs = [{"date": str(day), "actual_cost": float(actual or 0), "hypothetical_cost": hyp_by_day.get(str(day), 0.0)} for day, actual in daily_actual]
        cache_savings_usd = float(session.query(func.sum(RequestLog.tokens_saved_usd)).filter(RequestLog.cache_hit == True).scalar() or 0.0)
        routing_savings_usd = max(0.0, round(total_hypothetical_cost - total_actual_cost, 6))
        total_savings_usd = round(cache_savings_usd + routing_savings_usd, 6)
        average_quality = float(session.query(func.avg(RequestLog.quality_score)).filter(RequestLog.quality_score.isnot(None)).scalar() or 0.0)

        user_request_counts = dict(session.query(ApiKey.user_id, func.count(RequestLog.id)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id.isnot(None)).group_by(ApiKey.user_id).all())
        user_costs = dict(session.query(ApiKey.user_id, func.sum(RequestLog.cost_usd)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id.isnot(None)).group_by(ApiKey.user_id).all())
        all_user_ids = set(user_request_counts.keys()) | set(user_costs.keys())
        user_breakdown = [{"user_id": uid, "requests": user_request_counts.get(uid, 0), "cost_usd": round(float(user_costs.get(uid, 0) or 0), 6)} for uid in sorted(all_user_ids)]

        return {
            "total_requests": total_requests, "tier_counts": tier_counts, "tier_costs": tier_costs,
            "total_actual_cost": total_actual_cost, "total_hypothetical_cost": total_hypothetical_cost,
            "cache_hit_rate": cache_hit_rate, "fallback_count": fallback_count,
            "avg_latency_by_tier": avg_latency_by_tier, "daily_costs": daily_costs,
            "cache_savings_usd": cache_savings_usd, "routing_savings_usd": routing_savings_usd,
            "total_savings_usd": total_savings_usd, "average_quality": round(average_quality, 4),
            "user_breakdown": user_breakdown,
        }
    finally:
        session.close()


@router.get("/admin/keys")
def admin_keys(user_id: str = Depends(require_admin_any)):
    session = SessionLocal()
    try:
        rows = session.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
        return [
            {
                "id": r.id,
                "key": r.key[:8] + "..." + r.key[-4:] if len(r.key) > 16 else r.key,
                "name": r.name, "user_id": r.user_id, "is_active": r.is_active,
                "daily_budget_usd": r.daily_budget_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@router.get("/admin/logs")
def admin_logs(limit: int = 50, user_id: str = Depends(require_admin_any)):
    limit = max(1, min(limit, 200))
    session = SessionLocal()
    try:
        rows = session.query(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id, "query": r.query,
                "response": (r.response[:200] + "...") if r.response and len(r.response) > 200 else r.response,
                "tier": r.tier, "model_id": r.model_id, "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms, "cache_hit": r.cache_hit,
                "api_key_id": r.api_key_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@router.get("/admin/users")
def admin_users(user_id: str = Depends(require_admin_any)):
    session = SessionLocal()
    try:
        rows = session.query(ApiKey.user_id).filter(ApiKey.user_id.isnot(None)).distinct().all()
        result = []
        for (uid,) in rows:
            key_count = session.query(func.count(ApiKey.id)).filter(ApiKey.user_id == uid, ApiKey.is_active == True).scalar() or 0
            request_count = session.query(func.count(RequestLog.id)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id == uid).scalar() or 0
            total_cost = float(session.query(func.sum(RequestLog.cost_usd)).join(ApiKey, RequestLog.api_key_id == ApiKey.id).filter(ApiKey.user_id == uid).scalar() or 0.0)
            result.append({"user_id": uid, "active_keys": key_count, "total_requests": request_count, "total_cost_usd": round(total_cost, 6)})
        return result
    finally:
        session.close()
