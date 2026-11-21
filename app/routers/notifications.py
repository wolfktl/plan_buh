"""Серверные настройки оповещений (SMTP, Telegram-бот). Только администратор."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import notify
from ..database import get_db
from ..models import User
from ..schemas import NotificationSettingsIn, NotificationSettingsOut
from ..security import current_user, require_admin

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/settings", response_model=NotificationSettingsOut,
            dependencies=[Depends(require_admin)])
def get_settings(db: Session = Depends(get_db)):
    s = notify.get_settings(db)
    return NotificationSettingsOut(
        smtp_host=s.smtp_host, smtp_port=s.smtp_port, smtp_user=s.smtp_user,
        smtp_from=s.smtp_from, smtp_tls=s.smtp_tls,
        smtp_password_set=bool(s.smtp_password),
        telegram_bot_token_set=bool(s.telegram_bot_token),
        vapid_subject=s.vapid_subject,
    )


@router.put("/settings", dependencies=[Depends(require_admin)])
def update_settings(data: NotificationSettingsIn, db: Session = Depends(get_db)):
    s = notify.get_settings(db)
    s.smtp_host = data.smtp_host or None
    s.smtp_port = data.smtp_port or 587
    s.smtp_user = data.smtp_user or None
    s.smtp_from = data.smtp_from or None
    s.smtp_tls = data.smtp_tls
    # секреты: пустое значение = оставить прежнее
    if data.smtp_password:
        s.smtp_password = data.smtp_password
    if data.telegram_bot_token:
        s.telegram_bot_token = data.telegram_bot_token
    if data.vapid_subject:
        s.vapid_subject = data.vapid_subject
    db.commit()
    return {"ok": True}


@router.get("/vapid-public")
def vapid_public(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Публичный VAPID-ключ для подписки браузера на Web Push."""
    s = notify.ensure_vapid(db)
    return {"public_key": s.vapid_public}
