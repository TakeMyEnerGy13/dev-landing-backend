from fastapi import APIRouter, Depends

from app.dependencies import get_metrics_store
from app.handlers.metrics_store import MetricsStore

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/metrics", summary="Aggregated contact statistics")
async def metrics(store: MetricsStore = Depends(get_metrics_store)) -> dict:
    return store.snapshot()
