"""Auth endpoints: login, logout, me, change own password."""
from __future__ import annotations

from apiflask import APIBlueprint

from app.interface.deps import auth, auth_service, current_user, get_db
from app.interface.schemas import (
    ChangePasswordIn,
    LoginIn,
    MessageOut,
    TokenOut,
    UserOut,
)
from app.infrastructure.security.jwt import create_access_token

auth_bp = APIBlueprint("auth", __name__, url_prefix="/auth", tag="Auth")


@auth_bp.post("/login")
@auth_bp.input(LoginIn)
@auth_bp.output(TokenOut)
@auth_bp.doc(summary="Log in", description="Exchange username/password for a JWT access token.")
def login(json_data: dict):
    user = auth_service().authenticate(json_data["username"], json_data["password"])
    get_db().commit()  # persist any transparent password rehash
    token = create_access_token(user.id, user.role)
    return {"access_token": token, "token_type": "bearer"}


@auth_bp.post("/logout")
@auth_bp.output(MessageOut)
@auth_bp.auth_required(auth)
@auth_bp.doc(
    summary="Log out",
    description="Stateless JWT: the server has no session to destroy. The client "
    "discards the token. Returned for symmetry / audit logging.",
)
def logout():
    return {"message": "Logged out. Discard your access token."}


@auth_bp.get("/me")
@auth_bp.output(UserOut)
@auth_bp.auth_required(auth)
@auth_bp.doc(summary="Current user", description="Profile of the authenticated user.")
def me():
    return current_user()


@auth_bp.post("/change-password")
@auth_bp.input(ChangePasswordIn)
@auth_bp.output(MessageOut)
@auth_bp.auth_required(auth)
@auth_bp.doc(summary="Change own password")
def change_password(json_data: dict):
    user = current_user()
    auth_service().change_own_password(
        user.id, json_data["current_password"], json_data["new_password"]
    )
    get_db().commit()
    return {"message": "Password changed successfully."}
