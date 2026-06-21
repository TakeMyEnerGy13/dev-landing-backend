import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class MetricsStore:
    def __init__(self, path: str):
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write({"total": 0, "by_category": {}, "by_sentiment": {}, "last_updated": None})

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"total": 0, "by_category": {}, "by_sentiment": {}, "last_updated": None}

    def _write(self, data: dict) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    async def increment(self, category: str, sentiment: str) -> None:
        async with self._lock:
            data = self._read()
            data["total"] += 1
            data["by_category"][category] = data["by_category"].get(category, 0) + 1
            data["by_sentiment"][sentiment] = data["by_sentiment"].get(sentiment, 0) + 1
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._write(data)

    def snapshot(self) -> dict:
        return self._read()
