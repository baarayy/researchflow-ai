"""Logging setup. Every record carries the current research session id (if any)."""

import logging
from contextvars import ContextVar

session_id_var: ContextVar[str] = ContextVar("session_id", default="-")


class _SessionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = session_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_SessionFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [session=%(session_id)s] %(name)s: %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # httpx logs every request URL at INFO, which is noisy and may include query strings.
    logging.getLogger("httpx").setLevel(logging.WARNING)
