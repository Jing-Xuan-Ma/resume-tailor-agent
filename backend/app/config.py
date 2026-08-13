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
    CORS_ORIGIN_REGEX: str = ""
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://resume_agent:resume_agent_dev@localhost:5432/resume_agent"
    )
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

    # LLM — primary provider selection
    LLM_PROVIDER: str = "sensenova"
    # When preferred provider fails (503/429/timeout), try other configured keys.
    LLM_FAILOVER: bool = True

    # ── OpenAI-compatible providers ──────────────────────────
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""

    DEEPSEEK_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    XAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    FIREWORKS_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    HF_TOKEN: str = ""
    COPILOT_GITHUB_TOKEN: str = ""
    OPENCODE_API_KEY: str = ""
    ZAI_API_KEY: str = ""
    MINIMAX_API_KEY: str = ""
    MOONSHOT_API_KEY: str = ""
    XIAOMI_API_KEY: str = ""
    MIMO_API_KEY: str = ""
    CLOUDFLARE_API_KEY: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""
    ANT_LING_API_KEY: str = ""
    KIMI_API_KEY: str = ""
    QWEN_TOKEN_PLAN_API_KEY: str = ""
    RADIUS_API_KEY: str = ""
    # yiling gateway (router.c.yiling.top) — separate key scoped to glm-5.2 only
    YILING_GLM_API_KEY: str = ""
    # SenseNova (商汤日日新) — OpenAI-compatible chat completions
    SENSENOVA_API_KEY: str = ""
    # Zhipu / BigModel (智谱) — OpenAI-compatible paas/v4
    BIGMODEL_API_KEY: str = ""
    ZHIPU_API_KEY: str = ""

    # ── Native protocol providers ────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GOOGLE_CLOUD_API_KEY: str = ""
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = ""

    # AZURE
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_BASE_URL: str = ""

    # ── LLM model defaults ───────────────────────────────────
    DEFAULT_TAILOR_MODEL: str = "deepseek-v4-flash"
    DEFAULT_PARSER_MODEL: str = "deepseek-v4-flash"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
    # Phase 2 evidence / anti-fabrication LLM pass (expensive). Off = skip for speed.
    ENABLE_EVIDENCE_GUARD: bool = True
    # Shopping cart batch: hybrid fast path (light LLM + strong content rewrite).
    SHOPPING_CART_FAST_PATH: bool = True
    # Cover letter uses light LLM by default (company + JD grounded).
    SHOPPING_CART_COVER_LLM: bool = True
    FAST_TAILOR_MODEL: str = "deepseek-v4-flash"
    CONTENT_TAILOR_MODEL: str = "deepseek-v4-flash"
    # Content rewrite: one LLM batch per resume module, run in parallel.
    CONTENT_REWRITE_PARALLEL_MODULES: bool = True
    # Soft timeout per cart item: mark stalled (keep generating) so UI can proceed.
    SHOPPING_CART_ITEM_SOFT_TIMEOUT_S: int = 180
    # Max concurrent jobs in one shopping-cart batch (also caps GLM fan-out).
    SHOPPING_CART_BATCH_CONCURRENCY: int = 2

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

    # ── Email (cold outreach) ────────────────────────────────
    EMAIL_PROVIDER: str = "smtp"
    """smtp (default) | gmail_api"""
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    GMAIL_CREDENTIALS_PATH: str = ""
    """Path to Google OAuth client JSON (for gmail_api provider)"""
    OUTREACH_COOLDOWN_HOURS: int = 72
    """Min hours between outreach emails to the same company"""
    APP_HOST_URL: str = "http://localhost:8000"
    """Public-facing host URL for unsubscribe links"""
    # Optional Hunter.io key for single-person email finder (user-click only).
    HUNTER_API_KEY: str = ""

    # Rate limits
    MAX_DAILY_APPLICATIONS: int = 20
    MAX_DAILY_EMAILS: int = 50
    ENABLE_AUTO_SUBMIT: bool = True
    ENABLE_BROWSER_AUTOMATION: bool = False
    # Playwright fill is retired; apply happens in Agent chat via MCP + skills.
    ENABLE_BROWSER_FILL_PAUSE: bool = False
    # When False (default), fill-pause always uses local ATS fixtures — never live boards.
    # Live Greenhouse (manual, one URL): ENABLE_BROWSER_FILL_PAUSE=true + ALLOW_LIVE_BROWSER_FILL=true
    # See artifacts/funnel/auto-apply-v2/LIVE_GREENHOUSE.md — Submit is still never clicked by the agent.
    ALLOW_LIVE_BROWSER_FILL: bool = False
    # Allow UI "I confirm Submit" after pause (audit only; does not click live Submit).
    ENABLE_USER_CONFIRM_SUBMIT: bool = True
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 30000
    # Auto-apply field mapping: rules-first is fast; LLM only when explicitly enabled.
    APPLY_FIELD_MAP_PREFER_LLM: bool = False

    # ATS account (Create Account / Sign In on company boards). Never commit real values.
    ATS_DEFAULT_EMAIL: str = ""
    ATS_FALLBACK_EMAIL: str = ""
    ATS_DEFAULT_PASSWORD: str = ""
    ATS_PASSWORD_MIN_LENGTH: int = 8
    ATS_PASSWORD_REQUIRE_UPPER: bool = True
    ATS_PASSWORD_REQUIRE_LOWER: bool = True
    ATS_PASSWORD_REQUIRE_DIGIT: bool = True
    ATS_PASSWORD_REQUIRE_SPECIAL: bool = True
    # Jobright job detail template for cart apply navigation (Phase 2+).
    JOBRIGHT_JOB_URL_TEMPLATE: str = "https://jobright.ai/jobs/info/{intern_job_id}"
    # Logged-in Jobright session for Original Job Post (Playwright storage_state JSON).
    # Prefer storage_state; cookies file is Cookie-Editor export fallback.
    # Empty = auto-detect data/jobright_storage_state.json / data/jobright_cookies.json.
    JOBRIGHT_STORAGE_STATE_PATH: str = ""
    JOBRIGHT_COOKIES_PATH: str = ""
    # Phase 2: scraped/resolver first; live Jobright click last (needs session cookies).
    CART_APPLY_LIVE_NAV: bool = False
    CART_APPLY_LIVE_NAV_FALLBACK: bool = True
    # Phase 3: live Playwright Apply → Autofill with Resume on company ATS.
    # Local file:// / sandbox fixtures always allowed; production ATS needs this or ALLOW_LIVE_BROWSER_FILL.
    CART_APPLY_LIVE_ENTRY: bool = False

    # Claude Desktop handoff (JD step → pinned Project). macOS + Accessibility required.
    # Project UUID from https://claude.ai/project/<uuid> — strongly recommended (instant deep link).
    CLAUDE_DESKTOP_PROJECT_ID: str = ""
    CLAUDE_DESKTOP_PROJECT_NAME: str = "Resume"
    # true = use UI-TARS screen-locate (slow, needs Screen Recording). Default false = heuristics.
    CLAUDE_DESKTOP_USE_VISION: bool = False
    # Hard cap for the whole handoff (seconds).
    CLAUDE_DESKTOP_TIMEOUT_S: int = 75

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
