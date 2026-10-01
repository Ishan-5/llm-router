import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from fastapi.testclient import TestClient
from router.main import app
from router.db import SessionLocal, ApiKey, RequestLog
from datetime import datetime

client = TestClient(app)

def _key(name):
    s = SessionLocal()
    k = ApiKey(key=f"rw_pa_{name}", name=name, is_active=True)
    s.add(k)
    s.commit()
    s.refresh(k)
    s.close()
    return k

def _clear(k):
    s = SessionLocal()
    s.query(RequestLog).filter(RequestLog.api_key_id == k.id).delete()
    s.commit()
    s.close()

def _log(k, **kw):
    d = {
        "api_key_id": k.id, "query": "q", "tier": "cheap", "model_id": "m",
        "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.001,
        "latency_ms": 100, "cache_hit": False, "fallback_used": False,
        "tokens_saved_usd": 0.0, "quality_judged": False,
        "created_at": datetime.utcnow(),
        "difficulty_score": 5.0,
    }
    d.update(kw)
    s = SessionLocal()
    s.add(RequestLog(**d))
    s.commit()
    s.close()

def test_policy_analytics_basic():
    k = _key("pa1")
    _clear(k)
    for _ in range(3):
        _log(k)
    res = client.get("/policy-analytics", headers={"Authorization": f"Bearer {k.key}"})
    assert res.status_code == 200
    j = res.json()
    assert j["analyzed_requests"] == 3
    assert "caveat" in j
    assert "models" in j
    assert len(j["models"]) == 3
    ids = {m["id"] for m in j["models"]}
    assert ids == {"emma", "lisa", "kate"}
    for m in j["models"]:
        assert m["available"] in (True, False)
        if m["available"]:
            assert "traffic" in m
            assert "cost_usd" in m
            assert "savings_pct" in m
            assert "eval" in m
            assert "cuts" in m

def test_policy_analytics_require_auth():
    res = client.get("/policy-analytics")
    assert res.status_code == 401
