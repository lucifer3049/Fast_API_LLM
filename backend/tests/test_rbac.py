"""RBAC permission matrix tests — every cell of PLAN §1.2 has allow/deny."""
from __future__ import annotations

import pytest

from app.domain.user import Permission, Role, role_has_permission

U, A, S = Role.USER, Role.ADMIN, Role.SUPER_ADMIN

# (permission, role) -> expected allow, covering the full matrix.
MATRIX_CASES = [
    # self-service: all roles
    (Permission.CHANGE_OWN_PASSWORD, U, True),
    (Permission.CHANGE_OWN_PASSWORD, A, True),
    (Permission.CHANGE_OWN_PASSWORD, S, True),
    (Permission.USE_CHAT, U, True),
    (Permission.USE_CHAT, A, True),
    (Permission.USE_CHAT, S, True),
    (Permission.MANAGE_OWN_CHATS, U, True),
    (Permission.MANAGE_OWN_CHATS, A, True),
    (Permission.MANAGE_OWN_CHATS, S, True),
    # create user (role=user): admin, super_admin
    (Permission.CREATE_USER, U, False),
    (Permission.CREATE_USER, A, True),
    (Permission.CREATE_USER, S, True),
    # list users: admin, super_admin
    (Permission.LIST_USERS, U, False),
    (Permission.LIST_USERS, A, True),
    (Permission.LIST_USERS, S, True),
    # toggle user active: admin, super_admin
    (Permission.TOGGLE_USER_ACTIVE, U, False),
    (Permission.TOGGLE_USER_ACTIVE, A, True),
    (Permission.TOGGLE_USER_ACTIVE, S, True),
    # create admin: super_admin only
    (Permission.CREATE_ADMIN, U, False),
    (Permission.CREATE_ADMIN, A, False),
    (Permission.CREATE_ADMIN, S, True),
    # toggle admin active: super_admin only
    (Permission.TOGGLE_ADMIN_ACTIVE, U, False),
    (Permission.TOGGLE_ADMIN_ACTIVE, A, False),
    (Permission.TOGGLE_ADMIN_ACTIVE, S, True),
    # promote user->admin: super_admin only
    (Permission.PROMOTE_USER_TO_ADMIN, U, False),
    (Permission.PROMOTE_USER_TO_ADMIN, A, False),
    (Permission.PROMOTE_USER_TO_ADMIN, S, True),
    # export all chats: super_admin only
    (Permission.EXPORT_ALL_CHATS, U, False),
    (Permission.EXPORT_ALL_CHATS, A, False),
    (Permission.EXPORT_ALL_CHATS, S, True),
]


@pytest.mark.parametrize("permission,role,expected", MATRIX_CASES)
def test_permission_matrix(permission, role, expected):
    assert role_has_permission(role, permission) is expected


def test_every_permission_is_in_matrix():
    """Guard against a new Permission being added without a matrix entry."""
    from app.domain.user import PERMISSION_MATRIX

    for permission in Permission:
        assert permission in PERMISSION_MATRIX
