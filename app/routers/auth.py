"""Аутентификация: первичная настройка, вход, двухфакторка."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import security
from ..database import get_db
from ..models import User
from ..schemas import Credentials, TotpCode

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _users_count(db: Session) -> int:
    return db.query(func.count(User.id)).scalar() or 0


@router.get("/status")
def auth_status(request: Request, db: Session = Depends(get_db)):
    """Состояние для фронта: нужна ли первичная настройка и кто вошёл."""
    needs_setup = _users_count(db) == 0
    user = None
    token = request.cookies.get(security.SESSION_COOKIE)
    if token:
        payload = security._decode(token)
        if payload and payload.get("scope") == "session":
            u = db.get(User, int(payload["sub"]))
            if u and u.is_active:
                user = {"username": u.username, "totp_enabled": u.totp_enabled,
                        "role": u.role}
    return {"needs_setup": needs_setup, "authenticated": user is not None, "user": user}


@router.post("/register")
def register(creds: Credentials, db: Session = Depends(get_db)):
    """Создание первого (администраторского) пользователя. Только когда БД пуста."""
    if _users_count(db) > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Регистрация закрыта: администратор уже создан")
    user = User(username=creds.username.strip(),
                password_hash=security.hash_password(creds.password),
                role="admin")  # первый пользователь — администратор
    db.add(user)
    db.commit()
    return {"ok": True}


@router.post("/login")
def login(creds: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == creds.username.strip()).first()
    if not user or not security.verify_password(creds.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный логин или пароль")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Учётная запись отключена")

    if user.totp_enabled:
        # Пароль верный — выдаём промежуточный токен и просим код 2FA.
        security.set_preauth_cookie(response, user.id)
        return {"ok": True, "totp_required": True, "need_setup_2fa": False}

    # 2FA ещё не настроена — пускаем, но требуем настроить.
    security.set_session_cookie(response, user.id)
    return {"ok": True, "totp_required": False, "need_setup_2fa": True}


@router.post("/login/totp")
def login_totp(body: TotpCode, response: Response,
               user: User = Depends(security.preauth_user)):
    if not security.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный код подтверждения")
    security.set_session_cookie(response, user.id)
    response.delete_cookie(security.PREAUTH_COOKIE, path="/")
    return {"ok": True}


@router.post("/2fa/init")
def totp_init(user: User = Depends(security.current_user),
              db: Session = Depends(get_db)):
    """Сгенерировать секрет и QR. Подтверждение — в /2fa/verify."""
    if user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Двухфакторная аутентификация уже включена")
    secret = security.new_totp_secret()
    user.totp_secret = secret
    db.commit()
    uri = security.totp_uri(secret, user.username)
    return {"secret": secret, "otpauth_uri": uri, "qr": security.qr_png_data_uri(uri)}


@router.post("/2fa/verify")
def totp_verify(body: TotpCode, user: User = Depends(security.current_user),
                db: Session = Depends(get_db)):
    if not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Сначала инициализируйте 2FA")
    if not security.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный код — проверьте время на устройстве")
    user.totp_enabled = True
    db.commit()
    return {"ok": True}


@router.post("/2fa/disable")
def totp_disable(body: TotpCode, user: User = Depends(security.current_user),
                 db: Session = Depends(get_db)):
    """Отключить 2FA. Требует действующий код для подтверждения."""
    if not user.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Двухфакторная аутентификация не включена")
    if not security.verify_totp(user.totp_secret, body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неверный код")
    user.totp_enabled = False
    user.totp_secret = None
    db.commit()
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    security.clear_auth_cookies(response)
    return {"ok": True}
