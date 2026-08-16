import asyncio
import logging
import httpx
import ipaddress
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, String
from router.db import SessionLocal, RequestLog, ApiKey, AlertRule
from router.config import ALLOWED_ORIGINS
from router.openai_compat import router as openai_compat_router
from router.routes.route import router as route_router
from router.routes.keys import router as keys_router
from router.routes.config import router as config_router
from router.routes.stats import router as stats_router
from router.routes.alerts import router as alerts_router
from router.routes.admin import router as admin_router
from router.routes.settings import router as settings_router
from router.routes.news import router as news_router

log = logging.getLogger("routewise")

# re-export for test patches that reference router.main.*
from router.routes.route import check_cache, get_tier, add_to_cache, call_with_failover  # noqa: F401

ALERT_COOLDOWN_SECONDS = 3600


def _check_and_fire_alerts():
    session = SessionLocal()
    try:
        rules = session.query(AlertRule).filter(AlertRule.is_active == True).all()
        if not rules:
            return
        now = datetime.utcnow()
        today_start = datetime.combine(now.date(), datetime.min.time())
        hour_ago = now - timedelta(hours=1)

        for rule in rules:
            if rule.last_fired_at and (now - rule.last_fired_at).total_seconds() < ALERT_COOLDOWN_SECONDS:
                continue
            breached = False
            payload = {"alert_type": rule.alert_type, "threshold": rule.threshold}

            if rule.alert_type == "daily_spend":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                spent = float(session.query(func.sum(RequestLog.cost_usd)).filter(RequestLog.api_key_id.in_(key_ids), RequestLog.created_at >= today_start).scalar() or 0.0)
                payload["current_value"] = round(spent, 6)
                payload["message"] = f"Daily spend ${spent:.4f} exceeded threshold ${rule.threshold:.4f}"
                breached = spent >= rule.threshold

            elif rule.alert_type == "error_rate":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                total = session.query(func.count(RequestLog.id)).filter(RequestLog.api_key_id.in_(key_ids), RequestLog.created_at >= hour_ago).scalar() or 0
                errors = session.query(func.count(RequestLog.id)).filter(RequestLog.api_key_id.in_(key_ids), RequestLog.created_at >= hour_ago, RequestLog.tier == "failed").scalar() or 0
                rate = (errors / total * 100) if total > 0 else 0.0
                payload["current_value"] = round(rate, 2)
                payload["message"] = f"Error rate {rate:.1f}% exceeded threshold {rule.threshold:.1f}%"
                breached = rate >= rule.threshold

            elif rule.alert_type == "latency":
                key_ids = [k.id for k in session.query(ApiKey.id).filter(func.cast(ApiKey.user_id, String) == rule.user_id, ApiKey.is_active == True).all()]
                avg_latency = float(session.query(func.avg(RequestLog.latency_ms)).filter(RequestLog.api_key_id.in_(key_ids), RequestLog.created_at >= hour_ago, RequestLog.tier != "failed").scalar() or 0.0)
                payload["current_value"] = round(avg_latency, 1)
                payload["message"] = f"Avg latency {avg_latency:.0f}ms exceeded threshold {rule.threshold:.0f}ms"
                breached = avg_latency >= rule.threshold

            if breached:
                try:
                    httpx.post(rule.webhook_url, json=payload, timeout=5, follow_redirects=False)
                    rule.last_fired_at = now
                    session.commit()
                    log.info("Alert fired: %s for user %s", rule.alert_type, rule.user_id)
                except Exception as e:
                    log.warning("Webhook delivery failed for rule %s: %s", rule.id, e)
    except Exception as e:
        log.warning("Alert checker error: %s", e)
    finally:
        session.close()

# ThreadPoolExecutor for running blocking tasks in the background
executor = ThreadPoolExecutor()

# Lifespan event to preload ML models and start alert loop

@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    try:
        import sys
        sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'src'))
        from predict_difficulty import preload_models
        preload_models()
        log.info("ML models loaded successfully")
    except Exception as e:
        log.warning("ML model preload failed: %s", e)

    async def _alert_loop():
        while True:
            await asyncio.sleep(300)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, _check_and_fire_alerts)
            except Exception as e:
                log.warning("Alert loop error: %s", e)

    task = asyncio.create_task(_alert_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE", "HEAD"],
    allow_headers=["*"],
)

app.include_router(openai_compat_router)
app.include_router(route_router)
app.include_router(keys_router)
app.include_router(config_router)
app.include_router(stats_router)
app.include_router(alerts_router)
app.include_router(admin_router)
app.include_router(settings_router)
app.include_router(news_router)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    from router.db import SessionLocal, RequestLog
    from router.circuit_breaker import get_all_stats
    from router.load_balancer import get_pool_stats
    from sqlalchemy import func
    from datetime import datetime, timedelta
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        total = session.query(func.count(RequestLog.id)).scalar() or 0
        total_1h = session.query(func.count(RequestLog.id)).filter(RequestLog.created_at >= hour_ago).scalar() or 0
        errors_1h = session.query(func.count(RequestLog.id)).filter(RequestLog.created_at >= hour_ago, RequestLog.tier == "failed").scalar() or 0
        cache_hits_1h = session.query(func.count(RequestLog.id)).filter(RequestLog.created_at >= hour_ago, RequestLog.cache_hit == True).scalar() or 0
        avg_latency = float(session.query(func.avg(RequestLog.latency_ms)).filter(RequestLog.created_at >= hour_ago, RequestLog.tier != "failed").scalar() or 0)
        total_cost = float(session.query(func.sum(RequestLog.cost_usd)).scalar() or 0)
        tier_counts_1h = dict(session.query(RequestLog.tier, func.count(RequestLog.id)).filter(RequestLog.created_at >= hour_ago).group_by(RequestLog.tier).all())
        return {
            "requests_total": total,
            "requests_1h": total_1h,
            "errors_1h": errors_1h,
            "error_rate_1h_pct": round(errors_1h / total_1h * 100, 2) if total_1h else 0,
            "cache_hits_1h": cache_hits_1h,
            "cache_hit_rate_1h_pct": round(cache_hits_1h / total_1h * 100, 2) if total_1h else 0,
            "avg_latency_ms_1h": round(avg_latency, 1),
            "total_cost_usd": round(total_cost, 6),
            "tier_counts_1h": tier_counts_1h,
            "circuit_breakers": get_all_stats(),
            "key_pools": get_pool_stats(),
        }
    finally:
        session.close()
