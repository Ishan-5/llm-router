"""
Run once to add user_id column to request_logs and api_keys tables.
Copies existing api_key.user_id into request_logs.user_id via a join.

Usage: python migrate_add_user_id.py
"""
import os
from sqlalchemy import create_engine, text

db_url = os.getenv("DATABASE_URL", "")
if not db_url:
    print("DATABASE_URL not set — skipping migration")
    exit(0)

engine = create_engine(db_url)
with engine.connect() as conn:
    # 1. Add user_id to api_keys (idempotent)
    try:
        conn.execute(text("ALTER TABLE api_keys ADD COLUMN user_id TEXT"))
        conn.commit()
        print("✓ Added user_id column to api_keys")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
            print("api_keys.user_id already exists — skipping")
        else:
            print(f"Migration failed (api_keys): {e}")

    # 2. Add index on api_keys.user_id (idempotent)
    try:
        conn.execute(text("CREATE INDEX ix_api_keys_user_id ON api_keys (user_id)"))
        conn.commit()
        print("✓ Created index on api_keys.user_id")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("Index ix_api_keys_user_id already exists — skipping")
        else:
            print(f"Index creation failed (api_keys): {e}")

    # 3. Add user_id to request_logs (idempotent)
    try:
        conn.execute(text("ALTER TABLE request_logs ADD COLUMN user_id TEXT"))
        conn.commit()
        print("✓ Added user_id column to request_logs")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
            print("request_logs.user_id already exists — skipping")
        else:
            print(f"Migration failed (request_logs): {e}")

    # 4. Add index on request_logs.user_id (idempotent)
    try:
        conn.execute(text("CREATE INDEX ix_request_logs_user_id ON request_logs (user_id)"))
        conn.commit()
        print("✓ Created index on request_logs.user_id")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            print("Index ix_request_logs_user_id already exists — skipping")
        else:
            print(f"Index creation failed (request_logs): {e}")

    # 5. Backfill request_logs.user_id from api_keys (safe to re-run)
    try:
        result = conn.execute(text("""
            UPDATE request_logs rl
            SET user_id = ak.user_id
            FROM api_keys ak
            WHERE rl.api_key_id = ak.id
              AND rl.user_id IS NULL
              AND ak.user_id IS NOT NULL
        """))
        conn.commit()
        print(f"✓ Backfilled user_id on {result.rowcount} request_logs rows")
    except Exception as e:
        print(f"Backfill skipped (may not be supported on this DB engine): {e}")
        # Fallback for SQLite (used in tests)
        try:
            result = conn.execute(text("""
                UPDATE request_logs
                SET user_id = (
                    SELECT user_id FROM api_keys WHERE api_keys.id = request_logs.api_key_id
                )
                WHERE user_id IS NULL
            """))
            conn.commit()
            print(f"✓ SQLite backfill: updated {result.rowcount} rows")
        except Exception as e2:
            print(f"SQLite backfill also failed: {e2}")

print("\nMigration complete.")
