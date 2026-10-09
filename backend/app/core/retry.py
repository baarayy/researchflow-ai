"""Timeouts + bounded retries for calls to external providers (LLM, search, embeddings)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError | ConnectionError):
        return True
    # Provider SDKs expose rate limits / 5xx as differently named classes; match by name so we
    # don't import every SDK here.
    name = type(exc).__name__.lower()
    return any(
        k in name for k in ("ratelimit", "timeout", "connection", "internalserver", "apierror")
    )


async def call_with_retries[T](
    fn: Callable[[], Awaitable[T]],
    *,
    what: str,
    timeout: float,
    retries: int,
    base_delay: float = 1.0,
) -> T:
    """Run `fn` with a per-attempt timeout; retry transient failures with exponential backoff."""
    last: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            if attempt == retries or not _is_retryable(exc):
                break
            delay = base_delay * 2**attempt
            logger.warning("%s failed (%s), retrying in %.1fs", what, type(exc).__name__, delay)
            await asyncio.sleep(delay)
    raise ExternalServiceError(f"{what} failed: {type(last).__name__}") from last
