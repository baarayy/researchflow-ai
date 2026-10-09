"""Request identity and throttling.

DEVELOPMENT-ONLY AUTH: the caller's identity is taken from the `X-User-Id` header (default
"dev-user"). This is enough to keep users' sessions and documents separated in the data model,
but it is NOT authentication. Replace `get_current_user` with real auth (OIDC/JWT) before any
deployment; config validation refuses to start in production with dev auth enabled.
"""

import re
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Header

from app.core.config import Settings, get_settings
from app.core.errors import RateLimited, Unauthorized

_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


async def get_current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    x_user_id: Annotated[str | None, Header()] = None,
) -> str:
    if not settings.dev_auth_enabled:
        raise Unauthorized("Authentication is not configured")
    user_id = x_user_id or "dev-user"
    if not _USER_ID_RE.match(user_id):
        raise Unauthorized("Invalid X-User-Id header")
    return user_id


CurrentUser = Annotated[str, Depends(get_current_user)]


class SlidingWindowRateLimiter:
    """In-memory per-user limiter for expensive POST endpoints.

    shortcut: per-process memory, so limits reset on restart and are not shared across replicas;
    use a reverse proxy or Redis-backed limiter for multi-instance deployments.
    """

    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.limit:
            raise RateLimited("Too many requests, please slow down")
        hits.append(now)


_limiter: SlidingWindowRateLimiter | None = None


async def rate_limit(
    user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    global _limiter
    if _limiter is None or _limiter.limit != settings.rate_limit_per_minute:
        _limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)
    _limiter.check(user)
