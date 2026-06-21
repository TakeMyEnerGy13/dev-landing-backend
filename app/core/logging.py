import json
import logging
from pathlib import Path

from app.config import get_settings

_CONFIGURED = False


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
        }
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload.update(event)
        elif record.getMessage():
            payload["message"] = record.getMessage()
        return json.dumps(payload, ensure_ascii=False)


def _build_logger(name: str, filename: str) -> logging.Logger:
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    for h in list(logger.handlers):
        h.close()
    logger.handlers.clear()

    handler = logging.FileHandler(data_dir / filename, encoding="utf-8")
    handler.setFormatter(JsonLineFormatter())
    logger.addHandler(handler)
    return logger


def setup_logging() -> None:
    global _CONFIGURED
    _build_logger("requests", "requests.log")
    _build_logger("app", "app.log")


def get_request_logger() -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        setup_logging()
        _CONFIGURED = True
    return logging.getLogger("requests")


def get_app_logger() -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        setup_logging()
        _CONFIGURED = True
    return logging.getLogger("app")
