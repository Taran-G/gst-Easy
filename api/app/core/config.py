import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "LedgerGraph"
    API_V1_STR: str = "/api/v1"
    
    # FalkorDB / Redis
    FALKORDB_HOST: str = os.getenv("FALKORDB_HOST", "localhost")
    FALKORDB_PORT: int = int(os.getenv("FALKORDB_PORT", "6380"))
    FALKORDB_PASSWORD: str = os.getenv("FALKORDB_PASSWORD", "")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Auth & Security
    JWT_SECRET: str = os.getenv("JWT_SECRET", "super-secret-jwt-key-for-ledgergraph-hackathon-2026")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # Mode & Keys
    MODE: str = os.getenv("MODE", "mock")  # mock | live
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Meta WhatsApp Cloud API
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_ACCESS_TOKEN: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "ledgergraph-verify-token-2026")
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")
    
    # Gmail / Email Automation Settings
    EMAIL_MODE: str = os.getenv("EMAIL_MODE", "prototype")  # prototype | live_gmail
    EMAIL_IMAP_SERVER: str = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")
    EMAIL_IMAP_PORT: int = int(os.getenv("EMAIL_IMAP_PORT", "993"))
    EMAIL_SMTP_SERVER: str = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
    EMAIL_SMTP_PORT: int = int(os.getenv("EMAIL_SMTP_PORT", "587"))
    EMAIL_USERNAME: str = os.getenv("EMAIL_USERNAME", "")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD", "")
    AUTOMATION_ENABLED: bool = os.getenv("AUTOMATION_ENABLED", "true").lower() == "true"
    AUTOMATION_INTERVAL_SECONDS: int = int(os.getenv("AUTOMATION_INTERVAL_SECONDS", "30"))

    # GSP Integration (GST Portal API)
    GSP_BASE_URL: str = os.getenv("GSP_BASE_URL", "https://api.gsp.nic.in")
    GSP_CLIENT_ID: str = os.getenv("GSP_CLIENT_ID", "")
    GSP_CLIENT_SECRET: str = os.getenv("GSP_CLIENT_SECRET", "")
    GSP_AUTH_TOKEN: str = os.getenv("GSP_AUTH_TOKEN", "")
    
    # TallyPrime HTTP Bridge
    TALLY_HOST: str = os.getenv("TALLY_HOST", "localhost")
    TALLY_PORT: int = int(os.getenv("TALLY_PORT", "9000"))
    
    # Security & Upload Limits
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "*")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15"))
    
    # Storage & Paths
    DATA_DIR: str = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "files"))
    FIXTURES_DIR: str = os.getenv("FIXTURES_DIR", str(Path(__file__).resolve().parent.parent.parent.parent / "fixtures"))
    RULES_PATH: str = os.getenv("RULES_PATH", str(Path(__file__).resolve().parent.parent.parent.parent / "rules" / "rules.yaml"))

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()

# Ensure data dir exists
os.makedirs(settings.DATA_DIR, exist_ok=True)
