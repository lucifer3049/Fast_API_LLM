"""Tests for the Day 6 observability bonuses: request-id correlation, the JSON
log formatter, and the readiness probe's DB + LLM checks.

The readiness DB check talks to the real engine (Postgres), so it's stubbed with
a fake engine here; the LLM check uses the default offline mock provider.
"""
from __future__ import annotations

import json
import logging

import pytest

from app import create_app
from app.infrastructure.logging import JsonFormatter


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        return None


class _FakeEngine:
    def connect(self):
        return _FakeConn()


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_response_carries_generated_request_id(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")  # a fresh id was generated


def test_inbound_request_id_is_echoed(client):
    resp = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert resp.headers.get("X-Request-ID") == "abc-123"


def test_readiness_reports_db_and_llm(client, monkeypatch):
    from app.interface.api import health

    monkeypatch.setattr(health, "engine", _FakeEngine())
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["llm"] == "ok"  # default mock provider


def test_readiness_degraded_when_llm_unavailable(client, monkeypatch):
    from app.interface.api import health

    monkeypatch.setattr(health, "engine", _FakeEngine())

    def _boom(_settings):
        raise RuntimeError("no api key")

    monkeypatch.setattr(health, "get_llm_provider", _boom)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["status"] == "degraded"
    assert body["checks"]["llm"].startswith("error")


def test_json_formatter_emits_structured_line():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request",
        args=(),
        exc_info=None,
    )
    record.request_id = "rid-1"
    record.method = "GET"
    record.path = "/health/ready"
    record.status = 200
    record.duration_ms = 1.23

    parsed = json.loads(formatter.format(record))
    assert parsed["message"] == "request"
    assert parsed["request_id"] == "rid-1"
    assert parsed["method"] == "GET"
    assert parsed["status"] == 200
    assert "ts" in parsed and "level" in parsed
