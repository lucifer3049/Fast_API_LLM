"""Admin / Super Admin endpoints (PLAN §1.2 matrix).

Each route carries a coarse `@require_permission` gate; the service performs the
fine-grained, target-role-dependent checks (e.g. only super_admin may toggle an
admin) and cross-role constraints.
"""
from __future__ import annotations

import uuid

from apiflask import APIBlueprint

from app.domain.user import Permission
from app.interface.deps import (
    auth,
    current_user,
    export_service,
    get_db,
    user_admin_service,
)
from app.interface.permissions import require_permission
from app.interface.schemas import CreateUserIn, ExportOut, SetActiveIn, UserOut

admin_bp = APIBlueprint("admin", __name__, url_prefix="/admin", tag="Admin")


@admin_bp.get("/users")
@admin_bp.auth_required(auth)
@admin_bp.output(UserOut(many=True))
@admin_bp.doc(summary="List all users")
@require_permission(Permission.LIST_USERS)
def list_users():
    return user_admin_service().list_users(current_user())


@admin_bp.post("/users")
@admin_bp.auth_required(auth)
@admin_bp.input(CreateUserIn)
@admin_bp.output(UserOut, status_code=201)
@admin_bp.doc(
    summary="Create a user",
    description="admin may create role=user; super_admin may also create role=admin. "
    "super_admin cannot be created via the API.",
)
@require_permission(Permission.CREATE_USER)
def create_user(json_data: dict):
    user = user_admin_service().create_user(
        current_user(),
        username=json_data["username"],
        password=json_data["password"],
        role=json_data["role"],
    )
    get_db().commit()
    return user


@admin_bp.patch("/users/<uuid:user_id>/active")
@admin_bp.auth_required(auth)
@admin_bp.input(SetActiveIn)
@admin_bp.output(UserOut)
@admin_bp.doc(
    summary="Activate / deactivate a user",
    description="admin may toggle role=user; super_admin may also toggle role=admin. "
    "super_admin accounts cannot be modified.",
)
@require_permission(Permission.TOGGLE_USER_ACTIVE)
def set_active(user_id: uuid.UUID, json_data: dict):
    user = user_admin_service().set_active(current_user(), user_id, json_data["is_active"])
    get_db().commit()
    return user


@admin_bp.post("/users/<uuid:user_id>/promote")
@admin_bp.auth_required(auth)
@admin_bp.output(UserOut)
@admin_bp.doc(summary="Promote a user to admin", description="super_admin only.")
@require_permission(Permission.PROMOTE_USER_TO_ADMIN)
def promote(user_id: uuid.UUID):
    user = user_admin_service().promote_to_admin(current_user(), user_id)
    get_db().commit()
    return user


@admin_bp.get("/export")
@admin_bp.auth_required(auth)
@admin_bp.output(ExportOut)
@admin_bp.doc(
    summary="Export all conversations (JSON)",
    description="super_admin only. Returns every user with their chat sessions "
    "and messages — a complete snapshot for archival / migration.",
)
@require_permission(Permission.EXPORT_ALL_CHATS)
def export_all():
    return export_service().export_all(current_user())
