"""
Run once to add the response column to the existing request_logs table.
Usage: python migrate_add_response_column.py
"""
import os
from sqlalchemy import create_engine, text

db_url = os.getenv("DATABASE_URL", "")
if not db_url:
    print("DATABASE_URL not set — skipping migration")
    exit(0)

engine = create_engine(db_url)
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE request_logs ADD COLUMN response TEXT"))
        conn.commit()
        print("✓ Added response column to request_logs")
    except Exception as e:
        if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
            print("response column already exists — nothing to do")
        else:
            print(f"Migration failed: {e}")
