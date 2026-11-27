"""Basic per-IP rate limiting (sliding one-minute window).

shortcut: in-memory, so limits are per process and reset on restart; use Redis or a proxy limit if you run several workers.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


HITS: dict[str, deque] = defaultdict(deque)  # client IP -> request times; module-level so tests can clear it


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, per_minute: int):
        super().__init__(app)
        self.per_minute = per_minute
        self.hits = HITS

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return JSONResponse({"detail": "Too many requests, slow down"}, status_code=429, headers={"Retry-After": "60"})
        q.append(now)
        return await call_next(request)
