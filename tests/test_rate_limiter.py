import pytest

from app.core.errors import RateLimitExceeded
from app.handlers.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_requests=3, window_seconds=600)
    for _ in range(3):
        await limiter.check("1.2.3.4")
    with pytest.raises(RateLimitExceeded) as exc:
        await limiter.check("1.2.3.4")
    assert exc.value.retry_after > 0


@pytest.mark.asyncio
async def test_separate_keys_independent():
    limiter = RateLimiter(max_requests=1, window_seconds=600)
    await limiter.check("a")
    await limiter.check("b")  # different key — must not raise
