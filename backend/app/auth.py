from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings, get_settings


SESSION_COOKIE_NAME = "ayqm_admin_session"
_password_hasher = PasswordHasher()


def require_auth_settings(settings: Settings | None = None) -> Settings:
    resolved = settings or get_settings()
    if not resolved.admin_password_hash or not resolved.session_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured",
        )
    return resolved


def verify_admin_password(password: str, settings: Settings | None = None) -> bool:
    resolved = require_auth_settings(settings)
    try:
        return _password_hasher.verify(resolved.admin_password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_session_token(settings: Settings | None = None) -> str:
    resolved = require_auth_settings(settings)
    return _serializer(resolved).dumps({"sub": "admin", "version": 1})


def valid_session_token(token: str | None, settings: Settings | None = None) -> bool:
    if not token:
        return False
    resolved = require_auth_settings(settings)
    try:
        payload = _serializer(resolved).loads(token, max_age=resolved.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return payload == {"sub": "admin", "version": 1}


def require_admin(request: Request) -> None:
    settings = require_auth_settings()
    if not valid_session_token(request.cookies.get(SESSION_COOKIE_NAME), settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="ayqm-admin-session")
