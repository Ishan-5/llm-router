# Forces an isolated SQLite DB for tests so they never touch the real Supabase/Postgres.
# Unconditional override (not setdefault) -- if DATABASE_URL is already set in the environment,
# setdefault would silently do nothing and tests would run against the real DB.
import os
import sys
import tempfile

_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["GROQ_API_KEY"] = "test-key-not-real"
os.environ["GROQ_JUDGE_API_KEY"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))