"""Application factory (apiflask).

Wires config, OpenAPI `/docs`, blueprints, request-scoped DB, and a uniform
mapping from application errors to HTTP responses (business rules return 4xx,
not 500). Chat/admin blueprints are registered here as they land in later phases.
"""
from __future__ import annotations

from apiflask import APIFlask
from flask import g

from app.application.errors import AppError
from app.infrastructure.config import Settings, get_settings


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

    _configure_cors(app, settings)

    from app.interface import deps

    deps.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)

    return app


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
