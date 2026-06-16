"""
Simple thread-safe in-memory cache with TTL support.
"""
import time
import threading


class TTLCache:
    """Dictionary-based cache with per-key time-to-live."""

    def __init__(self, default_ttl=300):
        """
        Args:
            default_ttl: Default TTL in seconds (5 minutes).
        """
        self._store = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl

    def get(self, key):
        """Get value from cache. Returns None if expired or missing."""
        with self._lock:
            if key in self._store:
                value, expiry = self._store[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._store[key]
        return None

    def set(self, key, value, ttl=None):
        """Set value in cache with optional custom TTL."""
        ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            self._store[key] = (value, time.time() + ttl)

    def delete(self, key):
        """Remove a key from cache."""
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()

    def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]


# Global cache instance
cache = TTLCache(default_ttl=300)
