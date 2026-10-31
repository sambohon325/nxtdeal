"""Minimal structured request evidence. Never log raw URLs, input or exception text."""
import json
import logging
import time
from uuid import uuid4

log = logging.getLogger("nxtdeal.requests")


def install(app):
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    @app.middleware("http")
    async def observe(request, call_next):
        request_id = uuid4().hex  # Do not trust caller-provided IDs in logs.
        request.state.request_id = request_id
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            # Route templates omit customer IDs, tokens and arbitrary 404 paths.
            template = getattr(route, "path", "unmatched")
            log.info(json.dumps({"event": "http_request", "service": "dealer_api",
                                 "request_id": request_id, "route": template,
                                 "method": request.method if request.method in {
                                     "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} else "OTHER",
                                 "status": status,
                                 "duration_ms": round((time.monotonic() - started) * 1000, 2)},
                                separators=(",", ":")))
