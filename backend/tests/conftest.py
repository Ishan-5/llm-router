# Configure isolated SQLite database for testing environment.
# Override DATABASE_URL unconditionally to ensure tests do not interact with the production database.
import os
import sys
import tempfile

import pytest
from unittest.mock import patch

_test_db_fd, _test_db_path = tempfile.mkstemp(suffix=".db")
os.close(_test_db_fd)

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db_path}"
os.environ["GROQ_API_KEY"] = "test-key-not-real"
os.environ["GROQ_JUDGE_API_KEY"] = ""

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(autouse=True)
def _quiet_background_cache_writes():
    """No-op the fire-and-forget add_to_cache calls.

    The routes dispatch add_to_cache to a background ThreadPoolExecutor
    (loop.run_in_executor). In tests those threads can still be lazily loading
    the MiniLM embedder when the interpreter begins shutting down, producing
    noisy 'cannot schedule new futures after interpreter shutdown' tracebacks
    after the suite finishes. Patching both call sites keeps output clean.
    """
    with patch("router.routes.route.add_to_cache", return_value=None), \
         patch("router.openai_compat.add_to_cache", return_value=None):
        yield