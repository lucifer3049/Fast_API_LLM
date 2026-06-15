"""Health check endpoints.

`/health` is a liveness probe (process up) — what the compose healthcheck polls,
so container health never depends on an external service. `/health/ready` is a
readiness probe that verifies the dependencies needed to actually serve traffic:
the DB connection and the LLM upstream (PLAN Day 6 Bonus).
"""
from __future__ import annotations

from apiflask import APIBlueprint
from sqlalchemy import text

from app.infrastructure.config import get_settings
from app.infrastructure.db.session import engine
from app.infrastructure.llm import get_llm_provider

health_bp = APIBlueprint("health", __name__, tag="Health")


@health_bp.get("/health")
@health_bp.doc(summary="Liveness probe", description="Returns ok if the process is up.")
def health():
    return {"status": "ok"}


@health_bp.get("/health/ready")
@health_bp.doc(
    summary="Readiness probe",
    description="Verifies DB connectivity and LLM upstream reachability.",
)
def readiness():
    checks: dict[str, str] = {}
    healthy = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure as unhealthy
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        get_llm_provider(get_settings()).health_check()
        checks["llm"] = "ok"
    except Exception as exc:  # noqa: BLE001 - missing key / upstream down → degraded
        checks["llm"] = f"error: {exc.__class__.__name__}"
        healthy = False

    status_code = 200 if healthy else 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}, status_code
