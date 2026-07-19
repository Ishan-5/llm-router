"""
Load balancer for multiple API keys per tier.

Supports:
- Comma-separated keys in env vars: GROQ_KEYS_CHEAP=gk_abc,gk_def,gk_ghi
- Round-robin rotation across available keys
- Rate limit detection: skips keys that got 429'd (30s cooldown)
- Falls back to single GROQ_API_KEY if no multi-key config exists
"""

import time
import threading
from collections import defaultdict


class KeyPool:
    """Thread-safe round-robin key pool with rate limit cooldown."""

    def __init__(self, keys: list[str], cooldown_seconds: int = 30):
        self._keys = keys
        self._index = 0
        self._cooldowns: dict[str, float] = {}  # key -> expiry timestamp
        self._last_used: str | None = None  # track last key used for rate limit reporting
        self._lock = threading.Lock()
        self._cooldown_seconds = cooldown_seconds

    def get_key(self) -> str | None:
        """Returns the next available key, or None if all are on cooldown."""
        with self._lock:
            now = time.time()
            # Clean expired cooldowns
            self._cooldowns = {k: v for k, v in self._cooldowns.items() if v > now}

            available = [k for k in self._keys if k not in self._cooldowns]
            if not available:
                return None

            key = available[self._index % len(available)]
            self._index += 1
            self._last_used = key
            return key

    def mark_rate_limited(self, key: str = None):
        """Mark a key as rate-limited (429). It will be skipped for cooldown_seconds."""
        with self._lock:
            target = key or self._last_used
            if target:
                self._cooldowns[target] = time.time() + self._cooldown_seconds

    def mark_rate_limited_from_exception(self, key: str, error: Exception):
        """Check if an exception is a rate limit error and mark accordingly."""
        error_str = str(error).lower()
        if "429" in error_str or "rate" in error_str or "limit" in error_str:
            self.mark_rate_limited(key)


# Global tier pools, initialized from env vars at import time
_tier_pools: dict[str, KeyPool] = {}


def init_load_balancer(groq_keys_cheap: str = "", groq_keys_mid: str = "", groq_keys_frontier: str = "", cooldown: int = 30):
    """Initialize key pools from comma-separated env var strings."""
    global _tier_pools

    def parse_keys(raw: str) -> list[str]:
        return [k.strip() for k in raw.split(",") if k.strip()]

    cheap_keys = parse_keys(groq_keys_cheap)
    mid_keys = parse_keys(groq_keys_mid)
    frontier_keys = parse_keys(groq_keys_frontier)

    if cheap_keys:
        _tier_pools["cheap"] = KeyPool(cheap_keys, cooldown)
    if mid_keys:
        _tier_pools["mid"] = KeyPool(mid_keys, cooldown)
    if frontier_keys:
        _tier_pools["frontier"] = KeyPool(frontier_keys, cooldown)

    total = len(cheap_keys) + len(mid_keys) + len(frontier_keys)
    if total > 0:
        print(f"[loadbalancer] Initialized with {len(cheap_keys)} cheap, {len(mid_keys)} mid, {len(frontier_keys)} frontier keys")


def get_key_for_tier(tier: str) -> str | None:
    """Get the next available key for a tier. Returns None if no pool configured."""
    pool = _tier_pools.get(tier)
    if pool is None:
        return None
    return pool.get_key()


def report_rate_limit(tier: str, key: str = None):
    """Report that a key got rate-limited (429). It will be skipped for cooldown."""
    pool = _tier_pools.get(tier)
    if pool:
        pool.mark_rate_limited(key)


def report_rate_limit_from_error(tier: str, error: Exception):
    """Check if error is rate-limit related and report it (uses last tracked key for tier)."""
    pool = _tier_pools.get(tier)
    if pool:
        pool.mark_rate_limited_from_exception(None, error)


def has_multi_key_support() -> bool:
    """Returns True if any tier has more than one key configured."""
    return any(len(pool._keys) > 1 for pool in _tier_pools.values())


def get_pool_stats() -> dict:
    """Return stats about key pools for debugging/monitoring."""
    stats = {}
    for tier, pool in _tier_pools.items():
        now = time.time()
        stats[tier] = {
            "total_keys": len(pool._keys),
            "available_keys": len([k for k in pool._keys if k not in pool._cooldowns or pool._cooldowns[k] <= now]),
            "cooldown_keys": len([k for k in pool._cooldowns if pool._cooldowns[k] > now]),
        }
    return stats
