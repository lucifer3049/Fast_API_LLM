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

    from app.interface import deps

    deps.init_app(app)
    _register_blueprints(app)
    _register_error_handlers(app)

    return app


def _register_blueprints(app: APIFlask) -> None:
    from app.interface.api.admin import admin_bp
    from app.interface.api.auth import auth_bp
    from app.interface.api.health import health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)


def _register_error_handlers(app: APIFlask) -> None:
    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError):
        # A failed business rule must not leave a half-applied transaction.
        db = g.pop("db", None)
        if db is not None:
            db.rollback()
            db.close()
        return {"message": exc.message}, exc.status_code
