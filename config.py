# -*- coding: utf-8 -*-
"""
Central Configuration & Environment Architecture - Stargate Delivery Enterprise
Supports Production & Development environments, secure session keys, and encrypted secrets.
"""
import os
from datetime import timedelta
import secure_env

# Load .env file automatically if present
secure_env.load_environment_file()


class BaseConfig:
    """إعدادات النظام الأساسية المستندة إلى بيئة التشغيل والخزنة الرقمية."""
    ENV = os.environ.get("STARGATE_ENV") or os.environ.get("FLASK_ENV") or "production"
    SECRET_KEY = secure_env.get_or_create_secret_key()
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or os.environ.get("STARGATE_DB_PATH") or os.path.join(secure_env.DATA_DIR, "stargate_production.db")
    UPDATE_URL = os.environ.get("UPDATE_URL", "https://raw.githubusercontent.com/YourUser/YourRepo/main/version.json")

    # Session & Security Settings
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Decrypt sensitive external secrets dynamically at runtime
    GEMINI_API_KEY = secure_env.decrypt_sensitive_value(os.environ.get("GEMINI_API_KEY"))
    TELEGRAM_BOT_TOKEN = secure_env.decrypt_sensitive_value(os.environ.get("TELEGRAM_BOT_TOKEN"))
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
    GDRIVE_SERVICE_ACCOUNT_JSON = secure_env.decrypt_sensitive_value(os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON"))
    GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")


class ProductionConfig(BaseConfig):
    """إعدادات بيئة الإنتاج المعتمدة (Production Hardened)."""
    DEBUG = False
    TESTING = False
    # يُفعّل تلقائياً إذا تم تحديد متغير البيئة أو كان السيرفر يعمل خلف HTTPS
    SESSION_COOKIE_SECURE = os.environ.get("STARGATE_SECURE_COOKIE", "false").lower() in ("true", "1", "yes") or (os.environ.get("HTTPS", "").lower() == "on")


class DevelopmentConfig(BaseConfig):
    """إعدادات بيئة التطوير والاختبار المحلي."""
    DEBUG = True
    TESTING = True
    SESSION_COOKIE_SECURE = False


# Active Config selection
ENV_NAME = os.environ.get("STARGATE_ENV") or os.environ.get("FLASK_ENV") or "production"
if ENV_NAME.lower() in ("dev", "development"):
    Config = DevelopmentConfig
else:
    Config = ProductionConfig
