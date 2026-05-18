"""
Request / response access logger.

Uses BaseHTTPMiddleware (same as the working temp branch).
Adds correlation ID per request via ContextVar.

What IS logged:
  - Method, path, status code, duration
  - WARNING for 4xx, ERROR for 5xx

What is NEVER logged:
  - Request/response bodies
  - Authorization, Cookie headers, API keys
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from utils.log import new_correlation_id

log = logging.getLogger("api.access")

_SKIP_PATHS = {"/health", "/favicon.ico", "/favicon.svg"}


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        cid   = new_correlation_id()
        start = time.perf_counter()

        log.info("→ %s %s", request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception as exc:
            ms = (time.perf_counter() - start) * 1000
            log.error("✗ %s %s  error=%s  %.0fms",
                      request.method, request.url.path, type(exc).__name__, ms,
                      exc_info=True)
            raise

        ms     = (time.perf_counter() - start) * 1000
        status = response.status_code
        response.headers["X-Correlation-Id"] = cid

        if status < 400:
            log.info("← %s %s  %d  %.0fms", request.method, request.url.path, status, ms)
        elif status < 500:
            log.warning("← %s %s  %d  %.0fms", request.method, request.url.path, status, ms)
        else:
            log.error("← %s %s  %d  %.0fms", request.method, request.url.path, status, ms)

        return response
