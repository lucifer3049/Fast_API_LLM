"""Application factory (apiflask).

Wires config, OpenAPI `/docs`, blueprints, request-scoped DB, and a uniform
mapping from application errors to HTTP responses (business rules return 4xx,
not 500). Chat/admin blueprints are registered here as they land in later phases.
"""
from __future__ import annotations

import logging
import time
import uuid

from apiflask import APIFlask
from flask import Response, g, request

from app.application.errors import AppError
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.logging import configure_logging


def create_app(settings: Settings | None = None) -> APIFlask:
    settings = settings or get_settings()

    app = APIFlask(
        __name__,
        title="LLM Chat API",
        version="0.1.0",
        docs_path="/docs",
    )
    app.config["DESCRIPTION"] = "Multi-user LLM chat web application API."
    app.config["AUTO_404_RESPONSE"] = True

    _configure_observability(app, settings)
    _configure_cors(app, settings)

    from app.interface import deps

    deps.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)

    return app


def _configure_observability(app: APIFlask, settings: Settings) -> None:
    """Structured JSON logging + per-request id correlation (PLAN Day 6 Bonus).

    Each request gets an id (inbound ``X-Request-ID`` header or a fresh uuid),
    echoed on the response and attached to every log line. One structured access
    log is emitted per request with method/path/status/duration; the noisy
    liveness probe is skipped.
    """
    configure_logging(settings.log_level)
    access_log = logging.getLogger("app.access")

    @app.before_request
    def _begin_request() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_start = time.perf_counter()

    @app.after_request
    def _end_request(response: Response) -> Response:
        request_id = g.get("request_id")
        if request_id:
            response.headers["X-Request-ID"] = request_id
        if request.path != "/health":  # don't log the periodic liveness probe
            start = g.get("request_start")
            duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
            access_log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "remote_addr": request.remote_addr,
                },
            )
        return response


def _configure_cors(app: APIFlask, settings: Settings) -> None:
    """Allow the separated Vue frontend to call the API cross-origin (PLAN Day 6).

    Only the configured origins are permitted; the Authorization header is
    allowed so the SPA can send the JWT bearer token. When the SPA is served
    same-origin (compose nginx) no origins need be configured.
    """
    origins = settings.cors_origins_list
    if not origins:
        return
    from flask_cors import CORS

    CORS(
        app,
        resources={r"/*": {"origins": origins}},
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        supports_credentials=False,
    )


def _register_blueprints(app: APIFlask) -> None:
    from app.interface.api.admin import admin_bp
    from app.interface.api.auth import auth_bp
    from app.interface.api.chat import chat_bp
    from app.interface.api.health import health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(chat_bp)


def _register_error_handlers(app: APIFlask) -> None:
    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError):
        # A failed business rule must not leave a half-applied transaction.
        db = g.pop("db", None)
        if db is not None:
            db.rollback()
            db.close()
        return {"message": exc.message}, exc.status_code
