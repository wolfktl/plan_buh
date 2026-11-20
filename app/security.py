"""Пароли, JWT-сессии, TOTP-двухфакторка, зависимости FastAPI."""
import base64
from datetime import datetime, timedelta, timezone
from io import BytesIO

import bcrypt
import jwt
import pyotp
import qrcode
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User

ALGORITHM = "HS256"
SESSION_COOKIE = "pb_session"
PREAUTH_COOKIE = "pb_preauth"


# ---------------- Пароли ----------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- JWT ----------------
def _make_token(payload: dict, ttl_min: int) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=ttl_min)
    return jwt.encode(data, settings.SECRET_KEY, algorithm=ALGORITHM)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def make_session_token(user_id: int) -> str:
    return _make_token({"sub": str(user_id), "scope": "session"}, settings.SESSION_TTL_MIN)


def make_preauth_token(user_id: int) -> str:
    return _make_token({"sub": str(user_id), "scope": "preauth"}, settings.PREAUTH_TTL_MIN)


def _set_cookie(response: Response, name: str, token: str, ttl_min: int):
    response.set_cookie(
        key=name, value=token, max_age=ttl_min * 60, httponly=True,
        secure=settings.COOKIE_SECURE, samesite=settings.COOKIE_SAMESITE, path="/",
    )


def set_session_cookie(response: Response, user_id: int):
    _set_cookie(response, SESSION_COOKIE, make_session_token(user_id), settings.SESSION_TTL_MIN)


def set_preauth_cookie(response: Response, user_id: int):
    _set_cookie(response, PREAUTH_COOKIE, make_preauth_token(user_id), settings.PREAUTH_TTL_MIN)


def clear_auth_cookies(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(PREAUTH_COOKIE, path="/")


# ---------------- TOTP (2FA) ----------------
def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, username: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name=settings.TOTP_ISSUER)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def qr_png_data_uri(data: str) -> str:
    img = qrcode.make(data)
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


# ---------------- Зависимости ----------------
def _user_from_cookie(request: Request, db: Session, cookie: str, scope: str) -> User | None:
    token = request.cookies.get(cookie)
    if not token:
        return None
    payload = _decode(token)
    if not payload or payload.get("scope") != scope:
        return None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active:
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Полноценно аутентифицированный пользователь (пароль + 2FA пройдены)."""
    user = _user_from_cookie(request, db, SESSION_COOKIE, "session")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Требуется вход")
    return user


def preauth_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Пользователь, прошедший пароль, но ещё не 2FA."""
    user = _user_from_cookie(request, db, PREAUTH_COOKIE, "preauth")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Сессия подтверждения истекла, войдите снова")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    """Доступ только для администраторов."""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Требуются права администратора")
    return user
