"""Фоновый воркер: рассылка напоминаний и привязка Telegram-чатов.

Запуск: python -m app.worker  (отдельный сервис в docker-compose).
Два цикла в разных потоках:
  * reminders_loop  — каждые REMINDER_INTERVAL секунд рассылает наступившие
    напоминания по заметкам;
  * telegram_loop   — long-poll getUpdates: ловит /start <code> и привязывает
    чат к аккаунту пользователя.
"""
import logging
import threading
import time

from . import notify, reminders
from .database import SessionLocal, init_db
from .models import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")

REMINDER_INTERVAL = 30  # секунд


def reminders_loop():
    while True:
        db = SessionLocal()
        try:
            n = reminders.process_due(db)
            if n:
                log.info("Отправлено напоминаний: %s", n)
        except Exception as e:  # noqa: BLE001
            log.exception("reminders: %s", e)
        finally:
            db.close()
        time.sleep(REMINDER_INTERVAL)


def _handle_update(db, s, update) -> int:
    msg = update.get("message") or {}
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if chat_id and text:
        parts = text.split()
        if parts and parts[0] == "/start" and len(parts) > 1:
            code = parts[1].strip()
        elif parts and parts[0] != "/start":
            code = parts[0].strip()
        else:
            code = ""
        user = (db.query(User).filter(User.telegram_link_code == code).first()
                if code else None)
        if user:
            user.telegram_chat_id = chat_id
            user.telegram_link_code = None
            db.commit()
            notify.send_telegram(
                s, chat_id,
                f"✅ Чат привязан к аккаунту «{user.username}». "
                "Напоминания будут приходить сюда.")
        elif text == "/start":
            notify.send_telegram(
                s, chat_id,
                "Привет! Чтобы привязать чат, нажмите «Привязать Telegram» "
                "в приложении и перейдите по ссылке.")
        else:
            notify.send_telegram(
                s, chat_id,
                "Код не найден. Сгенерируйте новую ссылку в приложении "
                "(Настройки → Мои каналы).")
    return update["update_id"] + 1


def telegram_loop():
    offset = None
    while True:
        db = SessionLocal()
        try:
            s = notify.get_settings(db)
            token = s.telegram_bot_token
            if not token:
                time.sleep(15)
                continue
            updates = notify.telegram_get_updates(token, offset, timeout=20)
            for u in updates:
                try:
                    offset = _handle_update(db, s, u)
                except Exception as e:  # noqa: BLE001
                    log.exception("telegram update: %s", e)
                    offset = u["update_id"] + 1
        except Exception as e:  # noqa: BLE001
            log.exception("telegram: %s", e)
            time.sleep(5)
        finally:
            db.close()


def main():
    init_db()
    db = SessionLocal()
    try:
        notify.ensure_vapid(db)
    finally:
        db.close()
    log.info("Воркер запущен (интервал напоминаний: %s с)", REMINDER_INTERVAL)
    threading.Thread(target=reminders_loop, daemon=True).start()
    telegram_loop()


if __name__ == "__main__":
    main()
