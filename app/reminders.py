"""Формирование и отправка напоминаний по заметкам.

Используется воркером (пакетная рассылка) и эндпоинтом тестового уведомления.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from . import notify
from .models import Note, PushSubscription, User


def _note_message(note: Note) -> str:
    d = note.note_date.strftime("%d.%m.%Y")
    msg = f"🔔 Напоминание: {note.title}\n📅 {d}"
    if note.text:
        msg += f"\n\n{note.text}"
    return msg


def dispatch_note(db: Session, note: Note) -> dict:
    """Отправить напоминание по заметке на выбранные каналы.
    Возвращает {channel: (ok, error)}."""
    user = db.get(User, note.user_id)
    if not user:
        return {}
    s = notify.get_settings(db)
    channels = {c for c in (note.remind_channels or "").split(",") if c}
    text = _note_message(note)
    subject = f"Напоминание: {note.title}"
    results: dict = {}

    if "email" in channels and user.email:
        results["email"] = notify.send_email(s, user.email, subject, text)
    if "tg" in channels and user.telegram_chat_id:
        results["tg"] = notify.send_telegram(s, user.telegram_chat_id, text)
    if "push" in channels:
        subs = db.query(PushSubscription).filter(
            PushSubscription.user_id == user.id).all()
        payload = {"title": "Напоминание", "body": note.title,
                   "date": note.note_date.isoformat()}
        for sub in subs:
            ok, err = notify.send_push(
                s, {"endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, payload)
            results[f"push:{sub.id}"] = (ok, err)
            if not ok and err and ("410" in err or "404" in err):
                db.delete(sub)  # подписка устарела — удаляем
    return results


def process_due(db: Session, now: datetime | None = None) -> int:
    """Разослать все наступившие напоминания. Возвращает число обработанных."""
    now = now or datetime.now()
    due = db.query(Note).filter(
        Note.remind_at.isnot(None),
        Note.remind_at <= now,
        Note.remind_sent.is_(False),
    ).all()
    for note in due:
        if note.remind_channels:
            dispatch_note(db, note)
        note.remind_sent = True
    db.commit()
    return len(due)
