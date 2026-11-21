"""Каналы доставки оповещений: Email (SMTP), Telegram, Web Push.

Все функции возвращают (ok: bool, error: str|None) и не бросают исключений,
чтобы сбой одного канала/получателя не ломал рассылку остальным.
"""
import base64
import json
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.orm import Session

from .models import NotificationSettings


# ---------------- Настройки (singleton) ----------------
def get_settings(db: Session) -> NotificationSettings:
    s = db.get(NotificationSettings, 1)
    if not s:
        s = NotificationSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def ensure_vapid(db: Session) -> NotificationSettings:
    """Гарантирует наличие VAPID-ключей для Web Push (генерирует при первом вызове)."""
    s = get_settings(db)
    if not s.vapid_private or not s.vapid_public:
        priv = ec.generate_private_key(ec.SECP256R1())
        priv_pem = priv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode("ascii")
        pub_point = priv.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        app_server_key = base64.urlsafe_b64encode(pub_point).rstrip(b"=").decode("ascii")
        s.vapid_private = priv_pem
        s.vapid_public = app_server_key
        db.commit()
        db.refresh(s)
    return s


# ---------------- Email ----------------
def send_email(s: NotificationSettings, to: str, subject: str, body: str):
    if not s.smtp_host or not s.smtp_from or not to:
        return False, "SMTP не настроен или не указан адрес"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("Планировщик бухгалтера", s.smtp_from))
        msg["To"] = to
        with smtplib.SMTP(s.smtp_host, s.smtp_port or 587, timeout=15) as srv:
            srv.ehlo()
            if s.smtp_tls:
                srv.starttls()
                srv.ehlo()
            if s.smtp_user:
                srv.login(s.smtp_user, s.smtp_password or "")
            srv.sendmail(s.smtp_from, [to], msg.as_string())
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# ---------------- Telegram ----------------
def send_telegram(s: NotificationSettings, chat_id: str, text: str):
    if not s.telegram_bot_token or not chat_id:
        return False, "Telegram-бот не настроен или чат не привязан"
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=15,
        )
        if r.status_code == 200 and r.json().get("ok"):
            return True, None
        return False, f"Telegram API: {r.status_code} {r.text[:200]}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def telegram_get_updates(token: str, offset: int | None = None, timeout: int = 20):
    """Long-poll getUpdates для привязки чатов. Возвращает список апдейтов."""
    try:
        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates",
                      params=params, timeout=timeout + 10)
        if r.status_code == 200 and r.json().get("ok"):
            return r.json().get("result", [])
    except Exception:  # noqa: BLE001
        pass
    return []


# ---------------- Web Push ----------------
def send_push(s: NotificationSettings, subscription: dict, payload: dict):
    if not s.vapid_private:
        return False, "VAPID не инициализирован"
    try:
        from pywebpush import webpush
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=s.vapid_private,
            vapid_claims={"sub": s.vapid_subject or "mailto:admin@example.com"},
        )
        return True, None
    except Exception as e:  # noqa: BLE001
        # 404/410 — подписка устарела; вызывающий код может её удалить
        status = getattr(getattr(e, "response", None), "status_code", None)
        return False, f"{status or ''} {e}".strip()
