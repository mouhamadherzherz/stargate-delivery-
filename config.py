import os

class Config:
    """Central configuration management reading from environment variables."""
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("STARGATE_SECRET_KEY") or "stargate-delivery-fallback-secret-2026"
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or os.environ.get("STARGATE_DB_PATH") or "data/stargate_production.db"
    
    # Administrative Setup Defaults (Read only from environment, never hardcoded in logic)
    ADMIN_INITIAL_USERNAME = os.environ.get("ADMIN_INITIAL_USERNAME", "stargate")
    ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "stargate@19701313")
    ADMIN_INITIAL_PIN = os.environ.get("ADMIN_INITIAL_PIN", "19701313")
    
    # External APIs
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GDRIVE_SERVICE_ACCOUNT_JSON = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID")
    
    # Session & Security Settings
    SESSION_PERMANENT = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
