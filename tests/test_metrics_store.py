import pytest

from app.handlers.metrics_store import MetricsStore


@pytest.mark.asyncio
async def test_increment_and_snapshot(tmp_path):
    store = MetricsStore(str(tmp_path / "metrics.json"))
    await store.increment("sales", "positive")
    await store.increment("sales", "negative")
    snap = store.snapshot()
    assert snap["total"] == 2
    assert snap["by_category"]["sales"] == 2
    assert snap["by_sentiment"]["positive"] == 1
    assert snap["last_updated"] is not None
