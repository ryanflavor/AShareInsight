"""Simple in-memory cache implementation for AShareInsight.

This module provides a basic TTL-based cache for storing
search results and reducing database load.
"""

import asyncio
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any

from src.infrastructure.monitoring import track_cache_hit, track_cache_miss

# Cache entry format: (value, expiry_time)
CacheEntry = tuple[Any, float]


class SimpleCache:
    """Simple in-memory cache with TTL support.

    This cache implementation is thread-safe and supports
    automatic expiration of entries.
    """

    def __init__(self, default_ttl_seconds: int = 300, max_size: int = 1000):
        """Initialize the cache.

        Args:
            default_ttl_seconds: Default time-to-live in seconds (default: 5 minutes)
            max_size: Maximum number of entries to store (default: 1000)
        """
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # Cleanup every minute

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        async with self._lock:
            # Periodic cleanup
            await self._maybe_cleanup()

            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    # Update access order for LRU - O(1) with OrderedDict
                    self._cache.move_to_end(key)
                    track_cache_hit()
                    return value
                else:
                    # Expired, remove it
                    del self._cache[key]

            track_cache_miss()
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Optional TTL override
        """
        ttl = ttl_seconds or self._default_ttl
        expiry = time.time() + ttl

        async with self._lock:
            # Check if we need to evict entries
            while len(self._cache) >= self._max_size:
                # Evict least recently used entry - O(1) with OrderedDict
                lru_key, _ = self._cache.popitem(last=False)

            # Set the new value and move to end (most recently used)
            self._cache[key] = (value, expiry)
            self._cache.move_to_end(key)

    async def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was found and deleted, False otherwise
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            self._cache.clear()

    async def size(self) -> int:
        """Get the number of entries in the cache."""
        async with self._lock:
            return len(self._cache)

    async def _maybe_cleanup(self) -> None:
        """Remove expired entries if cleanup interval has passed."""
        current_time = time.time()

        if current_time - self._last_cleanup > self._cleanup_interval:
            # Remove expired entries
            expired_keys = [
                key
                for key, (_, expiry) in self._cache.items()
                if current_time >= expiry
            ]

            for key in expired_keys:
                del self._cache[key]

            self._last_cleanup = current_time

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        # Thread-safe access to cache size
        async with self._lock:
            size = len(self._cache)
            last_cleanup = self._last_cleanup

        return {
            "size": size,
            "max_size": self._max_size,
            "default_ttl_seconds": self._default_ttl,
            "last_cleanup": datetime.fromtimestamp(last_cleanup).isoformat(),
            "utilization_percent": round(size / self._max_size * 100, 2)
            if self._max_size > 0
            else 0,
        }


# Global cache instance for search results
_search_cache = SimpleCache(
    default_ttl_seconds=300, max_size=1000
)  # 5 minutes TTL, 1000 entries max


def get_search_cache() -> SimpleCache:
    """Get the global search cache instance."""
    return _search_cache


def create_cache_key(operation: str, identifier: str, **kwargs) -> str:
    """Create a cache key from operation and parameters.

    Args:
        operation: Operation name
        identifier: Primary identifier
        **kwargs: Additional parameters

    Returns:
        Cache key string
    """
    parts = [operation, identifier]

    # Add sorted kwargs to ensure consistent keys
    for k, v in sorted(kwargs.items()):
        parts.append(f"{k}:{v}")

    return ":".join(parts)
