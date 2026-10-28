import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = os.getenv("APP_NAME", "FindAI API")
    APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_NAME: str = os.getenv("DB_NAME", "findai_db")
    DB_USER: str = os.getenv("DB_USER", "findai_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    )


settings = Settings()
