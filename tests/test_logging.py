import json
from pathlib import Path

from app.core.logging import setup_logging, get_request_logger


def test_request_logger_writes_json_line(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()

    setup_logging()
    logger = get_request_logger()
    logger.info("", extra={"event": {"method": "POST", "path": "/api/contact", "status": 200}})

    for h in logger.handlers:
        h.flush()
    line = Path(tmp_path, "requests.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    record = json.loads(line)
    assert record["method"] == "POST"
    assert record["path"] == "/api/contact"
    assert record["status"] == 200
