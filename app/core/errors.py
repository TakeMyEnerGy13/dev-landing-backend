from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_app_logger


class AppError(Exception):
    status_code: int = 500
    message: str = "Application error"

    def __init__(self, message: str | None = None):
        if message:
            self.message = message
        super().__init__(self.message)


class RateLimitExceeded(AppError):
    status_code = 429
    message = "Rate limit exceeded. Please try again later."

    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(self.message)


class AIServiceError(AppError):
    status_code = 502
    message = "AI service is temporarily unavailable."


class EmailDeliveryError(AppError):
    status_code = 502
    message = "Failed to deliver email notification."


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, RateLimitExceeded):
            headers["Retry-After"] = str(exc.retry_after)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "detail": exc.message, "request_id": _request_id(request)},
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        get_app_logger().error(
            "",
            extra={"event": {"kind": "unhandled_exception", "type": type(exc).__name__,
                             "detail": str(exc), "request_id": _request_id(request)}},
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "detail": "Internal server error",
                     "request_id": _request_id(request)},
        )
