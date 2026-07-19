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
        # Write key to stderr to avoid polluting stdout logs
        print(f"Created key for '{name}':", file=sys.stderr)
        print(f"  {key}", file=sys.stderr)
        if daily_budget_usd:
            print(f"  Daily budget: ${daily_budget_usd:.2f}", file=sys.stderr)
        else:
            print("  No daily budget cap", file=sys.stderr)
    finally:
        session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_api_key.py <name> [daily_budget_usd]", file=sys.stderr)
        sys.exit(1)
    name = sys.argv[1]
    if not name.strip():
        print("Error: name cannot be empty", file=sys.stderr)
        sys.exit(1)
    budget = None
    if len(sys.argv) > 2:
        try:
            budget = float(sys.argv[2])
            if budget <= 0:
                raise ValueError("budget must be positive")
        except ValueError as e:
            print(f"Error: invalid budget value '{sys.argv[2]}': {e}", file=sys.stderr)
            sys.exit(1)
    create_key(name.strip(), budget)