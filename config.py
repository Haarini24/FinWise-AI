import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    DATABASE_PATH = BASE_DIR / "database" / "finwise.db"

    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"