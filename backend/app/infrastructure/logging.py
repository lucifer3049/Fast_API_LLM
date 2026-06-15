"""Structured (JSON) logging with request-ID correlation (PLAN Day 6 Bonus).

Every log line is one JSON object on stdout, carrying the current request's id
so logs across a single request can be grepped together. The id comes from an
inbound ``X-Request-ID`` header (propagated from an upstream proxy/gateway) or is
generated per request; it is also echoed back on the response.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys

from flask import g, has_request_context

# Optional structured fields the access logger attaches via `extra=`.
_ACCESS_FIELDS = ("method", "path", "status", "duration_ms", "remote_addr")


def get_request_id() -> str:
    """Current request's correlation id, or "-" outside a request context."""
    if has_request_context():
        return g.get("request_id", "-")
    return "-"


class RequestIdFilter(logging.Filter):
    """Stamps each record with the active request id so the formatter can emit it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": dt.datetime.fromtimestamp(record.created, dt.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in _ACCESS_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    """Point the root logger at a single JSON stdout handler (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
