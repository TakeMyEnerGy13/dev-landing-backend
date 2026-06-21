import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware

_START_TIME = time.monotonic()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Dev Landing Backend", version="1.0.0")

    setup_logging()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    from app.api import contact, metrics
    app.include_router(contact.router)
    app.include_router(metrics.router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

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
