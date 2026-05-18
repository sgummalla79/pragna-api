import os
from pathlib import Path
from dotenv import load_dotenv

# Step 1: load .env to get APP_ENV (the environment selector)
load_dotenv()

# Step 2: load the environment-specific file (.env.dev, .env.test, etc.)
_app_env  = os.getenv("APP_ENV", "dev")
_env_file = Path(__file__).parent / f".env.{_app_env}"
if _env_file.exists():
    load_dotenv(_env_file, override=False)

# ── Database (PostgreSQL only) ────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))

# ── LLM ──────────────────────────────────────────────────────────────────────
PERPLEXITY_API_BASE: str = "https://api.perplexity.ai"

# ── Pipeline limits ───────────────────────────────────────────────────────────
MAX_REVISIONS: int           = int(os.getenv("MAX_REVISIONS", "5"))
MAX_DISCOVERY_QUESTIONS: int = int(os.getenv("MAX_DISCOVERY_QUESTIONS", "30"))

# ── File upload ───────────────────────────────────────────────────────────────
UPLOAD_DIR: str       = os.getenv("UPLOAD_DIR", "uploads")
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
MAX_PDF_PAGES: int    = int(os.getenv("MAX_PDF_PAGES", "50"))
ALLOWED_IMAGE_EXTS: list[str] = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
ALLOWED_DOC_EXTS: list[str]   = [".pdf", ".docx", ".doc", ".txt", ".md"]
