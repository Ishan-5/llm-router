import time
import threading
import logging

log = logging.getLogger("routewise.circuit_breaker")

CLOSED = "closed"
OPEN   = "open"
HALF   = "half"

# Demo "simulate outage" mode. When a tier is listed here, its breaker reports
# OPEN without needing real failures -- every request skips that tier and the
# failover chain exercises itself in front of an audience. In-memory only.
_chaos_tiers: set[str] = set()
_chaos_lock = threading.Lock()


def set_chaos(active: bool, tiers: list[str] | None = None):
    """Enable/disable outage simulation. With no tier list, trips every tier
    except 'gemini' so the independent last-resort provider stays up."""
    with _chaos_lock:
        if not active:
            _chaos_tiers.clear()
            return
        if tiers:
            _chaos_tiers.update(t for t in tiers)
        else:
            _chaos_tiers.update(("cheap", "mid", "frontier"))


def get_chaos() -> dict:
    with _chaos_lock:
        return {"active": bool(_chaos_tiers), "tiers": sorted(_chaos_tiers)}


class CircuitBreaker:
    def __init__(self, tier: str = "unknown", failure_threshold: int = 3, cooldown_seconds: int = 60):
        self.tier = tier
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._state = CLOSED
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == OPEN:
                if time.time() - self._opened_at >= self._cooldown_seconds:
                    self._state = HALF
                    log.info("Circuit HALF-OPEN — trying one request")
            return self._state

    def record_success(self):
        with self._lock:
            self._failures = 0
            if self._state != CLOSED:
                log.info("Circuit CLOSED — provider recovered")
            self._state = CLOSED
            self._opened_at = None

    def record_failure(self):
        with self._lock:
            self._failures += 1
            if self._state == HALF or self._failures >= self._failure_threshold:
                self._state = OPEN
                self._opened_at = time.time()
                log.warning("Circuit OPEN after %d failures — skipping for %ds",
                            self._failures, self._cooldown_seconds)

    def is_open(self) -> bool:
        if self.tier in _chaos_tiers:
            return True
        return self.state == OPEN

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "failures": self._failures,
                "opened_at": self._opened_at,
                "simulated": self.tier in _chaos_tiers,
            }


# One circuit breaker per tier — shared across all requests
_breakers: dict[str, CircuitBreaker] = {
    "cheap":    CircuitBreaker("cheap"),
    "mid":      CircuitBreaker("mid"),
    "frontier": CircuitBreaker("frontier"),
    "gemini":   CircuitBreaker("gemini"),
}


def get_breaker(tier: str) -> CircuitBreaker:
    return _breakers.get(tier, CircuitBreaker(tier))


def get_all_stats() -> dict:
    with _chaos_lock:
        return {tier: b.get_stats() for tier, b in _breakers.items()}
