# Configure isolated SQLite database for testing environment.
# Override DATABASE_URL unconditionally to ensure tests do not interact with the production database.
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