"""Configuration loaded from environment (.env) via Pydantic."""
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "Astrov"
    DEBUG: bool = False
    # Локальная разработка без Telegram: init_data=dev_local принимается при DEBUG=true
    ALLOW_DEV_AUTH: bool = False
    DEV_TELEGRAM_USER_ID: int = 999000001
    CORS_ALLOWED_ORIGINS: str = ""
    USE_NEW_ASTRO_ENGINE: bool = False
    SE_EPHE_PATH: str = ""
    REDIS_URL: str = ""
    NATAL_CHART_CACHE_TTL_DAYS: int = 365
    NATAL_INTERPRETATION_CACHE_TTL_DAYS: int = 30

    # Telegram (PROJECT_CONTEXT.md)
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    # Имя бота без @ для реферальных ссылок https://t.me/{username}?start=ref_
    TELEGRAM_BOT_USERNAME: str = ""
    TELEGRAM_INIT_DATA_MAX_AGE_SECONDS: int = 900
    TELEGRAM_INIT_DATA_CLOCK_SKEW_SECONDS: int = 60
    # URL Mini App (например ngrok: https://xxx.ngrok-free.dev)
    APP_URL: str = ""
    # Telegram engagement-напоминания (возврат в приложение). Пока выключено: тексты зададите отдельным списком.
    ENGAGEMENT_NUDGES_ENABLED: bool = False
    # Если задан - бот работает по webhook (один инстанс, без getUpdates). Иначе - polling.
    # В продакшене задать: https://ваш-домен.up.railway.app (без слэша в конце)
    WEBHOOK_BASE_URL: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""

    @field_validator("WEBHOOK_BASE_URL", mode="before")
    @classmethod
    def strip_webhook_base_url(cls, v: object) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        return s

    # Database (PostgreSQL)
    DATABASE_URL: Optional[str] = None
    DATABASE_PRIVATE_URL: Optional[str] = None

    # Персистентные файлы (аватары, support-вложения). Railway: том смонтировать на этот путь.
    # Пример: ASTROV_UPLOADS_DIR=/data/astrov-uploads
    ASTROV_UPLOADS_DIR: str = ""
    # Явный путь к каталогу Jinja-шаблонов (admin/, sqladmin/). Пусто: автопоиск от корня проекта и /app/templates.
    ASTROV_TEMPLATES_DIR: str = ""

    # Admin panel (SQLAdmin)
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_SESSION_SECRET: str = ""

    # OpenAI - основной провайдер (текст + vision)
    OPENAI_API_KEY: Optional[str] = None
    # Запасной по сканированию (vision): отдельный ключ GPT для анализа фото/ладони/совместимости
    OPENAI_GPT_API_KEY: str = ""

    # AI дополнительный (VseGPT и т.д.): primary, если OPENAI_API_KEY не задан
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""
    AI_TEXT_MODEL: str = ""
    AI_VISION_MODEL: str = ""
    # Диалог с тарологом: имя модели как в OpenAI API (см. документацию моделей). Неверное имя: повтор с AI_TEXT_MODEL.
    AI_TAROLOGIST_MODEL: str = "gpt-4o"
    # Интерпретация расклада (draw-batch, доработка карт): пусто = основная AI_TEXT_MODEL. Для объёмных текстов часто лучше сильная модель.
    AI_TAROT_INTERPRETATION_MODEL: str = ""
    # Совместимость по датам (POST /api/numerology/compatibility): интерпретация по мандалам
    AI_COMPATIBILITY_DATES_MODEL: str = "gpt-5.4-mini"

    # SKY-MAP.org для AstroMap (карта звездного неба по дате)
    SKYMAP_API_KEY: str = ""
    SKYMAP_BASE_URL: str = "http://server2.sky-map.org"
    SKYMAP_TIMEOUT_SECONDS: float = 30.0
    SKYMAP_MAX_RETRIES: int = 2

    # DeepSeek - запасной провайдер только для текста (в API нет vision)
    # Ключ: https://platform.deepseek.com/api_keys
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = ""
    DEEPSEEK_TEXT_MODEL: str = "deepseek-chat"

    # ЮKassa (оплата подписки и пополнение баланса)
    YOOKASSA_SHOP_ID: str = ""
    YOOKASSA_SECRET_KEY: str = ""
    YOOKASSA_WEBHOOK_SECRET: str = ""
    # Только СБП (redirect flow), без виджета и подписок
    YOOKASSA_SBP_ONLY: bool = False
    # Ставка комиссии ЮKassa в % (2.8–3.5 для карт, 0.4–2.2 для СБП - уточните в личном кабинете)
    YOOKASSA_COMMISSION_PERCENT: float = 3.5
    BILLING_CRON_SECRET: str = ""
    TAROT_IMAGE_ALLOWED_HOSTS: str = ""
    # URL приложения для return_url после оплаты (например https://t.me/astrov_bot/app или ваш домен)
    APP_URL: str = ""

    # Inworld TTS API. Без ключа - фронт использует Web Speech API.
    # Ключ: https://platform.inworld.ai/ → Settings → API Keys (Base64)
    INWORLD_API_KEY: str = ""
    # Голос: Dennis, Alex (м), Ashley (ж) и др. Список: GET /tts/v1/voices?filter=language=ru
    INWORLD_TTS_VOICE_ID: str = "Dennis"
    # Модель: inworld-tts-1.5-max (качество) или inworld-tts-1.5-mini (быстрее)
    INWORLD_TTS_MODEL: str = "inworld-tts-1.5-max"
    # Скорость речи: 0.5–1.5, 1.0 = нормально
    INWORLD_TTS_SPEAKING_RATE: float = 0.9


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
