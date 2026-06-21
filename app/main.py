import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware

_START_TIME = time.monotonic()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Dev Landing Backend", version="1.0.0")

    setup_logging()

    app.add_middleware(RequestLoggingMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "uptime_seconds": round(time.monotonic() - _START_TIME, 3),
            "ai_available": settings.ai_configured,
            "email_configured": settings.email_configured,
        }

    return app


app = create_app()
