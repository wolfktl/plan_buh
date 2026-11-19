"""Конфигурация приложения из переменных окружения."""
import os
import secrets


def _get_secret() -> str:
    key = os.getenv("SECRET_KEY")
    if not key:
        # Фолбэк для локального запуска. В проде ОБЯЗАТЕЛЬНО задайте SECRET_KEY.
        key = secrets.token_urlsafe(48)
        print("[WARN] SECRET_KEY не задан — сгенерирован временный ключ. "
              "Сессии сбросятся при перезапуске. Задайте SECRET_KEY в .env!")
    return key


class Settings:
    SECRET_KEY: str = _get_secret()
    # Срок жизни полной сессии (после ввода пароля и 2FA)
    SESSION_TTL_MIN: int = int(os.getenv("SESSION_TTL_MIN", "720"))  # 12 часов
    # Срок жизни промежуточного токена между паролем и вводом кода 2FA
    PREAUTH_TTL_MIN: int = int(os.getenv("PREAUTH_TTL_MIN", "5"))

    DB_PATH: str = os.getenv("DB_PATH", "/data/plan_buh.db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Отправлять cookie только по HTTPS. Включите за reverse-proxy с TLS.
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")
    COOKIE_SAMESITE: str = os.getenv("COOKIE_SAMESITE", "lax")

    # Название, которое увидит пользователь в приложении-аутентификаторе
    TOTP_ISSUER: str = os.getenv("TOTP_ISSUER", "ПланБух")

    APP_TITLE: str = os.getenv("APP_TITLE", "Планировщик бухгалтера")

    @property
    def sqlalchemy_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite:///{self.DB_PATH}"


settings = Settings()
