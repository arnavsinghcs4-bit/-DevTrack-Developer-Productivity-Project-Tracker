"""
In-memory sliding-window rate limiter for the authentication endpoints.

Design notes (interview talking points):

- **Sliding window, not fixed window.** Hits are stored as timestamps and
  anything older than the window is discarded on each check, so there is no
  fixed-window boundary burst (fixed windows allow 2x the limit across a
  boundary).
- **Thread safety.** FastAPI runs sync dependencies in a threadpool, so the
  hit dequeues are guarded by a lock.
- **Thread-correct timing.** The clock is injectable (`clock=`), which lets
  tests drive the window deterministically without sleeping.
- **Single-process storage.** Counters live in this process's memory. That
  is correct for one uvicorn worker and for the test suite; a multi-worker
  deployment must swap in shared storage (e.g. Redis). The interface is kept
  deliberately tiny (`check`/`reset`) to make that swap a one-file change.
- **Applied as a FastAPI dependency**, so tests override it exactly the way
  `get_db` is overridden: `app.dependency_overrides[auth_rate_limit]`.
"""

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request, status

from app.core.config import settings


class InMemoryRateLimiter:
    """Sliding-window counter keyed by an arbitrary string."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        """
        Records one hit for `key` and raises HTTP 429 (with a Retry-After
        header) when the sliding window is already exhausted. The rejected
        attempt is NOT recorded, so a blocked client cannot extend its own
        lockout by retrying in a tight loop.
        """
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= limit:
                retry_after = max(1, int(hits[0] + window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)

    def reset(self) -> None:
        """Clears all counters (used by tests and available for ops)."""
        with self._lock:
            self._hits.clear()


# Process-wide limiter instance (see module docstring for storage caveats).
limiter = InMemoryRateLimiter()


def auth_rate_limit(request: Request) -> None:
    """
    Per-IP sliding-window limiter for POST /auth/login and POST /auth/register.

    Limits and the enabled flag are read from settings at request time so
    deployments can tune them via environment variables (and tests can flip
    `RATE_LIMIT_ENABLED` without reimporting the app). The key includes the
    path, so login and register get independent budgets.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return

    path = request.url.path
    if path.endswith("/login"):
        limit = settings.RATE_LIMIT_LOGIN_ATTEMPTS
    elif path.endswith("/register"):
        limit = settings.RATE_LIMIT_REGISTER_ATTEMPTS
    else:
        return  # not an auth-limited endpoint

    client_ip = request.client.host if request.client else "unknown"
    limiter.check(
        key=f"auth:{path}:{client_ip}",
        limit=limit,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )
