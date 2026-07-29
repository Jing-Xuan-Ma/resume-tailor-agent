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

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://resume_agent:resume_agent_dev@localhost:5432/resume_agent"

    # Vector DB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_PREFIX: str = "resume_agent_"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM — primary provider selection
    LLM_PROVIDER: str = "openai"

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
    CLOUDFLARE_API_KEY: str = ""
    CLOUDFLARE_ACCOUNT_ID: str = ""
    ANT_LING_API_KEY: str = ""
    KIMI_API_KEY: str = ""
    QWEN_TOKEN_PLAN_API_KEY: str = ""
    RADIUS_API_KEY: str = ""

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

    # Rate limits
    MAX_DAILY_APPLICATIONS: int = 20
    MAX_DAILY_EMAILS: int = 10
    ENABLE_AUTO_SUBMIT: bool = True
    ENABLE_BROWSER_AUTOMATION: bool = False
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT_MS: int = 30000

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.APP_ENV == "development":
            return ["*"]
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return origins if origins != ["*"] else ["*"]


settings = Settings()
