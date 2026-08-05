"""
Application configuration via Pydantic Settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000"
    # Allow Chrome/Edge extension origins (Side Panel → localhost API).
    CORS_ORIGIN_REGEX: str = r"^chrome-extension://.*"
    FRONTEND_BASE_URL: str = "http://localhost:3000"
    # Shared secret for extension → API writes (empty = allow in development only).
    EXTENSION_BRIDGE_TOKEN: str = "dev-extension-token"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://resume_agent:resume_agent_dev@localhost:5432/resume_agent"
    # Local MVP uses SQLite (`data/app.db`). Set `postgres` for cloud / compose.
    STORAGE_BACKEND: str = "sqlite"

    # Vector DB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_PREFIX: str = "resume_agent_"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Commercial / cloud gates (Phase 5) — all off by default
    ENABLE_MULTI_TENANT: bool = False
    ENABLE_BILLING: bool = False
    # Outreach: mailto/mark-sent by default; Gmail/SMTP only when explicitly enabled
    ENABLE_GMAIL_SEND: bool = False

    # LLM
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    GEMINI_API_KEY: str = ""
    BIGMODEL_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    DEFAULT_TAILOR_MODEL: str = "gpt-5.5"
    DEFAULT_PARSER_MODEL: str = "gpt-5.5"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Security
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Job Discovery Providers
    ADZUNA_APP_ID: str = ""
    ADZUNA_API_KEY: str = ""
    JOB_DISCOVERY_MIN_SCORE: float = 0.5
    JOB_DISCOVERY_TOP_N: int = 10

    # JR-1 local job index (read/write separation)
    JOB_INDEX_ENABLED: bool = True
    JOB_INDEX_INGEST_ON_STARTUP: bool = False
    # Slower cadence reduces JobSpy/Adzuna rate-limit risk.
    JOB_INDEX_INGEST_INTERVAL_MINUTES: int = 30
    # Comma-separated; "auto" expands to category queries. Prefer DA/BA-focused set in .env.
    JOB_INDEX_DEFAULT_QUERIES: str = "auto"
    # Empty = no location filter (onsite/hybrid/remote). Was "Remote" and starved US roles.
    JOB_INDEX_DEFAULT_LOCATION: str = ""
    JOB_INDEX_INGEST_LIMIT: int = 50
    # Freshness window passed to JobSpy (and used as ingest default).
    JOB_INDEX_HOURS_OLD: int = 72
    # Conservative JobSpy sites first (LinkedIn often blocks; Google Jobs often
    # times out from restricted networks). Comma-separated.
    JOB_INDEX_JOBSPY_SITES: str = "indeed"
    # JobSpy hard-crashes inside the API's Python 3.14 + numpy build (ACCESS_VIOLATION).
    # Run scrapes in a subprocess under JOBSPY_PYTHON (dedicated 3.12 venv).
    JOB_INDEX_ENABLE_JOBSPY: bool = True
    # Absolute path to the JobSpy worker interpreter (e.g. backend/venv312/Scripts/python.exe).
    # Empty → fall back to sys.executable (only safe when that runtime is 3.11/3.12).
    JOBSPY_PYTHON: str = ""
    # Adzuna often returns truncated ad teasers — off by default for quality ingest.
    JOB_INDEX_ENABLE_ADZUNA: bool = False
    # Reject thin/ad listings before upsert (Jobright-style real JD gate).
    JOB_INDEX_QUALITY_GATE: bool = True
    JOB_INDEX_MIN_JD_CHARS: int = 500

    # Rate limits
    MAX_DAILY_APPLICATIONS: int = 20
    MAX_DAILY_EMAILS: int = 50
    ENABLE_AUTO_SUBMIT: bool = True
    ENABLE_BROWSER_AUTOMATION: bool = False
    # Fill forms + screenshot, never click Submit (Sprint D sandbox / gated preview)
    ENABLE_BROWSER_FILL_PAUSE: bool = True
    # When False (default), fill-pause always uses local ATS fixtures — never live boards.
    # Live Greenhouse (manual, one URL): ENABLE_BROWSER_FILL_PAUSE=true + ALLOW_LIVE_BROWSER_FILL=true
    # See artifacts/funnel/auto-apply-v2/LIVE_GREENHOUSE.md — Submit is still never clicked by the agent.
    ALLOW_LIVE_BROWSER_FILL: bool = False
    # Allow UI "I confirm Submit" after pause (audit only; does not click live Submit).
    ENABLE_USER_CONFIRM_SUBMIT: bool = True
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 30000

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.APP_ENV == "development":
            return ["*"]
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return origins if origins != ["*"] else ["*"]

    @property
    def CORS_ORIGIN_REGEX_VALUE(self) -> str | None:
        raw = (self.CORS_ORIGIN_REGEX or "").strip()
        return raw or None


settings = Settings()
