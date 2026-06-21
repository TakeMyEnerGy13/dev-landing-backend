import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_request_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid4().hex
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        client_ip = request.client.host if request.client else "-"
        get_request_logger().info(
            "",
            extra={"event": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "ip": client_ip,
                "status": response.status_code,
                "latency_ms": latency_ms,
            }},
        )
        response.headers["X-Request-ID"] = request_id
        return response
