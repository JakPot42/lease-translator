import os

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
DEMO_MODE: bool = os.getenv("DEMO_MODE", "True").lower() in ("true", "1", "yes")
CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./lease_translator.db")
APP_TITLE: str = "Lease Translator"
