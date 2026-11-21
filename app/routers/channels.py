"""Личные каналы оповещений пользователя: email, Telegram, браузерные push."""
import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import notify
from ..database import get_db
from ..models import PushSubscription, User
from ..schemas import ChannelsOut, EmailIn, EndpointIn, PushSubscriptionIn
from ..security import current_user

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/me", response_model=ChannelsOut)
def my_channels(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = notify.get_settings(db)
    cnt = db.query(func.count(PushSubscription.id)).filter(
        PushSubscription.user_id == user.id).scalar() or 0
    return ChannelsOut(
        email=user.email, telegram_linked=bool(user.telegram_chat_id),
        push_count=cnt, telegram_available=bool(s.telegram_bot_token),
        smtp_available=bool(s.smtp_host and s.smtp_from),
    )


@router.put("/email")
def set_email(data: EmailIn, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    user.email = (data.email or "").strip() or None
    db.commit()
    return {"ok": True}


@router.post("/telegram/link")
def telegram_link(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = notify.get_settings(db)
    if not s.telegram_bot_token:
        raise HTTPException(status_code=400,
                            detail="Администратор ещё не настроил Telegram-бота")
    code = secrets.token_hex(3)
    user.telegram_link_code = code
    db.commit()
    username = None
    try:
        r = httpx.get(f"https://api.telegram.org/bot{s.telegram_bot_token}/getMe",
                      timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            username = r.json()["result"].get("username")
    except Exception:  # noqa: BLE001
        pass
    link = f"https://t.me/{username}?start={code}" if username else None
    return {"code": code, "bot_username": username, "link": link}


@router.delete("/telegram")
def telegram_unlink(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.telegram_chat_id = None
    user.telegram_link_code = None
    db.commit()
    return {"ok": True}


@router.post("/push/subscribe")
def push_subscribe(data: PushSubscriptionIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    ex = db.query(PushSubscription).filter(
        PushSubscription.endpoint == data.endpoint).first()
    if ex:
        ex.user_id = user.id
        ex.p256dh = data.p256dh
        ex.auth = data.auth
    else:
        db.add(PushSubscription(user_id=user.id, endpoint=data.endpoint,
                                p256dh=data.p256dh, auth=data.auth))
    db.commit()
    return {"ok": True}


@router.post("/push/unsubscribe")
def push_unsubscribe(data: EndpointIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    db.query(PushSubscription).filter(
        PushSubscription.user_id == user.id,
        PushSubscription.endpoint == data.endpoint).delete()
    db.commit()
    return {"ok": True}


@router.post("/test")
def test_notification(user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    """Отправить тестовое уведомление по всем настроенным каналам пользователя."""
    s = notify.get_settings(db)
    text = "✅ Тестовое уведомление от Планировщика бухгалтера"
    results: dict = {}
    if user.email and s.smtp_host:
        results["email"] = notify.send_email(s, user.email, "Тест", text)
    if user.telegram_chat_id:
        results["tg"] = notify.send_telegram(s, user.telegram_chat_id, text)
    subs = db.query(PushSubscription).filter(
        PushSubscription.user_id == user.id).all()
    for sub in subs:
        ok, err = notify.send_push(
            s, {"endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
            {"title": "Тест", "body": text})
        results[f"push:{sub.id}"] = (ok, err)
    return {
        "sent": [k for k, v in results.items() if v[0]],
        "errors": {k: v[1] for k, v in results.items() if not v[0]},
    }
