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
    
    # Storage & Paths
    DATA_DIR: str = os.getenv("DATA_DIR", str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "files"))
    FIXTURES_DIR: str = os.getenv("FIXTURES_DIR", str(Path(__file__).resolve().parent.parent.parent.parent / "fixtures"))
    RULES_PATH: str = os.getenv("RULES_PATH", str(Path(__file__).resolve().parent.parent.parent.parent / "rules" / "rules.yaml"))

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()

# Ensure data dir exists
os.makedirs(settings.DATA_DIR, exist_ok=True)
