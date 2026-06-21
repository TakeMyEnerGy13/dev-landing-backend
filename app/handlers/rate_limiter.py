import asyncio
import time

from app.core.errors import RateLimitExceeded


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self._window
        async with self._lock:
            timestamps = [t for t in self._hits.get(key, []) if t > cutoff]
            if len(timestamps) >= self._max:
                retry_after = int(timestamps[0] + self._window - now) + 1
                self._hits[key] = timestamps
                raise RateLimitExceeded(retry_after=max(retry_after, 1))
            timestamps.append(now)
            self._hits[key] = timestamps
