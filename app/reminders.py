"""Формирование и отправка напоминаний по заметкам.

Используется воркером (пакетная рассылка) и эндпоинтом тестового уведомления.
"""
import calendar
from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from . import notify
from .models import Note, PushSubscription, User


def add_period(dt, repeat: str):
    """Сдвинуть дату/время на один период повтора. dt — date или datetime."""
    if repeat == "daily":
        from datetime import timedelta
        return dt + timedelta(days=1)
    if repeat == "weekly":
        from datetime import timedelta
        return dt + timedelta(days=7)
    if repeat == "monthly":
        m, y = dt.month + 1, dt.year
        if m > 12:
            m, y = 1, y + 1
        last = calendar.monthrange(y, m)[1]
        return dt.replace(year=y, month=m, day=min(dt.day, last))
    if repeat == "yearly":
        try:
            return dt.replace(year=dt.year + 1)
        except ValueError:            # 29 февраля
            return dt.replace(year=dt.year + 1, day=28)
    return None


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
    """Разослать все наступившие напоминания. Возвращает число обработанных.

    Разовая заметка после отправки помечается remind_sent=True.
    Повторяющаяся — её remind_at сдвигается на следующий период (чтобы
    напоминание пришло и в следующий раз), пока не превышен repeat_until.
    """
    now = now or datetime.now()
    due = db.query(Note).filter(
        Note.remind_at.isnot(None),
        Note.remind_at <= now,
        or_(Note.remind_sent.is_(False),
            and_(Note.repeat.isnot(None), Note.repeat != "none")),
    ).all()
    for note in due:
        if note.remind_channels:
            dispatch_note(db, note)
        if note.repeat and note.repeat != "none":
            nxt = add_period(note.remind_at, note.repeat)
            if nxt is None or (note.repeat_until and nxt.date() > note.repeat_until):
                note.remind_at = None
                note.remind_sent = True
            else:
                note.remind_at = nxt   # следующее напоминание
        else:
            note.remind_sent = True
    db.commit()
    return len(due)
