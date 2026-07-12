"""
Run this manually to create an API key. Not exposed as an endpoint --
key generation should be an admin action, not something the public API does.

Usage:
    python scripts/create_api_key.py "my-test-key" 5.00
    python scripts/create_api_key.py "acme-corp-demo"   # no budget cap
"""
import sys
import secrets
sys.path.append(".")
from router.db import SessionLocal, ApiKey


def create_key(name: str, daily_budget_usd: float | None = None):
    key = f"rw_{secrets.token_urlsafe(24)}"
    session = SessionLocal()
    try:
        record = ApiKey(key=key, name=name, daily_budget_usd=daily_budget_usd, is_active=True)
        session.add(record)
        session.commit()
        print(f"Created key for '{name}':")
        print(f"  {key}")
        if daily_budget_usd:
            print(f"  Daily budget: ${daily_budget_usd:.2f}")
        else:
            print("  No daily budget cap")
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_api_key.py <name> [daily_budget_usd]")
        sys.exit(1)
    name = sys.argv[1]
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else None
    create_key(name, budget)