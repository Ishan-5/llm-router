"""
Runs before any test imports router modules. Forces an isolated, disposable
SQLite DB so tests NEVER touch the real Supabase/Postgres database.

IMPORTANT: this is an unconditional override, not setdefault(). If
DATABASE_URL is already set in your real environment (likely, since you use
it for local dev against Supabase), setdefault() would silently do nothing
and tests would run against your real database -- which is exactly what
happened before this fix, causing duplicate-key errors from real rows
accumulating in Supabase across repeated test runs.

A fresh temp file is created per test session (not a shared/fixed path),
so there's no possibility of stale data from a previous run causing
collisions either.
"""
import os
import sys
import tempfile

_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["GROQ_API_KEY"] = "test-key-not-real"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))