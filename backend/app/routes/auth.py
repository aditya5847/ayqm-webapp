from fastapi import APIRouter, HTTPException, Request, Response, status

from ..auth import SESSION_COOKIE_NAME, create_session_token, require_auth_settings, valid_session_token, verify_admin_password
from ..config import get_settings
from ..schemas import AdminLogin, AdminSession


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AdminSession)
def login(request: AdminLogin, response: Response) -> dict[str, bool]:
    settings = require_auth_settings()
    if not verify_admin_password(request.password, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(settings),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"authenticated": True}


@router.get("/session", response_model=AdminSession)
def session(request: Request) -> dict[str, bool]:
    settings = require_auth_settings()
    return {"authenticated": valid_session_token(request.cookies.get(SESSION_COOKIE_NAME), settings)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
