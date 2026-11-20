from __future__ import annotations
from fastapi import Header, HTTPException, Request
from . import settings
from .firebase_service import auth_verify_id_token, app_check_verify_token


def require_team_member(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in with an authorised team account.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = auth_verify_id_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Your sign-in token is invalid or expired.")
    if claims.get("teamMember") is not True:
        raise HTTPException(status_code=403, detail="This account is not authorised for the private laboratory.")
    return claims


def verify_public_app_check(request: Request) -> None:
    if not settings.REQUIRE_APP_CHECK:
        return
    token = request.headers.get("X-Firebase-AppCheck", "")
    if not token:
        raise HTTPException(status_code=401, detail="App Check token is required.")
    try:
        app_check_verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="App Check verification failed.")
