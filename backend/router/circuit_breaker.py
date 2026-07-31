import time
import threading
import logging

log = logging.getLogger("routewise.circuit_breaker")

CLOSED = "closed"
OPEN   = "open"
HALF   = "half"


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 60):
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
        return self.state == OPEN

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "failures": self._failures,
                "opened_at": self._opened_at,
            }


# One circuit breaker per tier — shared across all requests
_breakers: dict[str, CircuitBreaker] = {
    "cheap":    CircuitBreaker(),
    "mid":      CircuitBreaker(),
    "frontier": CircuitBreaker(),
    "gemini":   CircuitBreaker(),
}


def get_breaker(tier: str) -> CircuitBreaker:
    return _breakers.get(tier, CircuitBreaker())


def get_all_stats() -> dict:
    return {tier: b.get_stats() for tier, b in _breakers.items()}
