"""
Unified LLM client — multi-provider, multi-protocol.

Inspired by pi-ai's provider + auth + models architecture.

Every provider is a self-contained unit:
  - owns its model catalog / defaults
  - owns its auth (env var resolution)
  - owns its wire protocol (OpenAI-compatible, Anthropic Messages, Google Gemini, etc.)

Usage:
    from app.core.llm_client import get_llm, get_llm_models, get_configured_providers

    # Auto-detect first configured provider & return a langchain LLM
    llm = get_llm()
    response = await llm.ainvoke([("human", "Hello")])

    # Explicit provider
    llm = get_llm(provider="deepseek", model="deepseek-chat")

    # List what's available
    models = get_llm_models()        # all known models
    ready = get_configured_providers()  # which providers have API keys set
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ApiType = Literal["openai", "anthropic", "google", "mistral", "bedrock"]

# ---------------------------------------------------------------------------
# Provider metadata — pi-ai inspired "provider object"
# ---------------------------------------------------------------------------

@dataclass
class ProviderInfo:
    """Static metadata for one LLM provider (analogous to pi-ai's Provider)."""

    id: str
    name: str
    api_type: ApiType
    env_var: str
    base_url: str | None = None
    base_url_env: str | None = None        # optional env var override for base_url
    default_model: str = ""
    extra_env_vars: dict[str, str] = field(default_factory=dict)
    """Additional env vars needed, e.g. AZURE_OPENAI_API_VERSION -> value"""

    @property
    def effective_base_url(self) -> str | None:
        if self.base_url_env:
            return self._get_env(self.base_url_env) or self.base_url
        return self.base_url

    def _get_env(self, var: str) -> str | None:
        """Check settings first (pydantic loads .env), then os.environ."""
        val = getattr(settings, var, None) or os.getenv(var)
        return val if val else None

    def is_configured(self) -> bool:
        """Check whether the essential API key env var is set (pi-ai's findEnvKeys)."""
        if self.env_var and self._get_env(self.env_var):
            return True
        # Some providers have ambient auth (Bedrock, Vertex) — check extra hints
        if self.id == "amazon-bedrock":
            return bool(self._get_env("AWS_PROFILE") or self._get_env("AWS_ACCESS_KEY_ID"))
        if self.id == "google-vertex":
            return bool(self._get_env("GOOGLE_CLOUD_API_KEY") or (
                self._get_env("GOOGLE_CLOUD_PROJECT") and self._get_env("GOOGLE_CLOUD_LOCATION")
            ))
        return False

    def api_key(self) -> str | None:
        """Resolve the API key from env (pi-ai's getEnvApiKey)."""
        return self._get_env(self.env_var)

    def all_env(self) -> dict[str, str | None]:
        """Return {var_name: value} for every env var this provider cares about."""
        result: dict[str, str | None] = {self.env_var: self.api_key()}
        for var in self.extra_env_vars:
            result[var] = os.getenv(var)
        return result


# ---------------------------------------------------------------------------
# Provider catalog — 38+ providers, pi-ai style
# ---------------------------------------------------------------------------

# OpenAI-compatible providers (use ChatOpenAI with base_url override)
OPENAI_COMPAT_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(id="openai",         name="OpenAI",              api_type="openai",   env_var="OPENAI_API_KEY",                      default_model="gpt-4o-mini",
                  base_url_env="OPENAI_BASE_URL"),
    ProviderInfo(id="deepseek",       name="DeepSeek",            api_type="openai",   env_var="DEEPSEEK_API_KEY",    base_url="https://api.deepseek.com/v1",                    default_model="deepseek-chat"),
    ProviderInfo(id="groq",           name="Groq",                api_type="openai",   env_var="GROQ_API_KEY",        base_url="https://api.groq.com/openai/v1",                default_model="llama-3.3-70b-versatile"),
    ProviderInfo(id="cerebras",       name="Cerebras",            api_type="openai",   env_var="CEREBRAS_API_KEY",    base_url="https://api.cerebras.ai/v1",                    default_model="llama-3.3-70b"),
    ProviderInfo(id="xai",            name="xAI (Grok)",          api_type="openai",   env_var="XAI_API_KEY",         base_url="https://api.x.ai/v1",                           default_model="grok-2-1212"),
    ProviderInfo(id="openrouter",     name="OpenRouter",          api_type="openai",   env_var="OPENROUTER_API_KEY",  base_url="https://openrouter.ai/api/v1",                  default_model="auto"),
    ProviderInfo(id="together",       name="Together AI",         api_type="openai",   env_var="TOGETHER_API_KEY",    base_url="https://api.together.xyz/v1",                   default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ProviderInfo(id="fireworks",      name="Fireworks AI",        api_type="openai",   env_var="FIREWORKS_API_KEY",   base_url="https://api.fireworks.ai/inference/v1",         default_model="accounts/fireworks/models/llama-v3p3-70b-instruct"),
    ProviderInfo(id="mistral",        name="Mistral",             api_type="mistral",  env_var="MISTRAL_API_KEY",     base_url="https://api.mistral.ai/v1",                     default_model="open-mistral-nemo"),
    ProviderInfo(id="nvidia",         name="NVIDIA NIM",          api_type="openai",   env_var="NVIDIA_API_KEY",      base_url="https://integrate.api.nvidia.com/v1",           default_model="meta/llama-3.3-70b-instruct"),
    ProviderInfo(id="huggingface",    name="Hugging Face",        api_type="openai",   env_var="HF_TOKEN",            base_url="https://api-inference.huggingface.co/v1/",      default_model="meta-llama/Llama-3.3-70B-Instruct"),
    ProviderInfo(id="github-copilot", name="GitHub Copilot",      api_type="openai",   env_var="COPILOT_GITHUB_TOKEN",base_url="https://api.githubcopilot.com/v1",              default_model="gpt-4o-copilot"),
    ProviderInfo(id="opencode",       name="OpenCode Zen",        api_type="openai",   env_var="OPENCODE_API_KEY",    base_url="https://api.opencode.ai/v1",                    default_model="opencode-zen"),
    ProviderInfo(id="opencode-go",    name="OpenCode Go",         api_type="openai",   env_var="OPENCODE_API_KEY",    base_url="https://api.opencode.ai/v1",                    default_model="opencode-go"),  # shares OPENCODE_API_KEY
    ProviderInfo(id="zai",            name="ZAI Coding Plan",     api_type="openai",   env_var="ZAI_API_KEY",         base_url="https://api.z.ai/v1",                          default_model="zai-coding"),
    ProviderInfo(id="minimax",        name="MiniMax",             api_type="openai",   env_var="MINIMAX_API_KEY",     base_url="https://api.minimax.chat/v1",                  default_model="MiniMax-Text-01"),
    ProviderInfo(id="moonshotai",     name="Moonshot AI (Kimi)",  api_type="openai",   env_var="MOONSHOT_API_KEY",    base_url="https://api.moonshot.cn/v1",                    default_model="kimi-k2"),
    # Xiaomi MiMo — OpenAI-compatible. Official pay-as-you-go base URL:
    # https://api.xiaomimimo.com/v1  (models: mimo-v2.5-pro, mimo-v2.5)
    ProviderInfo(id="xiaomi",         name="Xiaomi MiMo",         api_type="openai",   env_var="XIAOMI_API_KEY",      base_url="https://api.xiaomimimo.com/v1",                 default_model="mimo-v2.5-pro",
                  base_url_env="XIAOMI_BASE_URL"),
    ProviderInfo(id="mimo",           name="Xiaomi MiMo",         api_type="openai",   env_var="MIMO_API_KEY",        base_url="https://api.xiaomimimo.com/v1",                 default_model="mimo-v2.5-pro",
                  base_url_env="MIMO_BASE_URL"),
    ProviderInfo(id="cloudflare",     name="Cloudflare Workers AI",api_type="openai",  env_var="CLOUDFLARE_API_KEY",  base_url=None,                                            default_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                  extra_env_vars={"CLOUDFLARE_ACCOUNT_ID": "Cloudflare Account ID"}),
    ProviderInfo(id="ant-ling",       name="Ant Ling",            api_type="openai",   env_var="ANT_LING_API_KEY",    base_url="https://api.antling.ai/v1",                    default_model="ant-ling-v1"),
    ProviderInfo(id="kimi-coding",    name="Kimi For Coding",     api_type="openai",   env_var="KIMI_API_KEY",        base_url="https://api.moonshot.cn/v1",                   default_model="kimi-coding"),
    ProviderInfo(id="qwen-token",     name="Qwen Token Plan",     api_type="openai",   env_var="QWEN_TOKEN_PLAN_API_KEY", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", default_model="qwen-plus"),
    ProviderInfo(id="radius",         name="Radius",              api_type="openai",   env_var="RADIUS_API_KEY",      base_url="https://api.radius.ai/v1",                     default_model="radius-default"),
]

# Non-OpenAI-compatible providers (use native SDKs via langchain)
NON_OPENAI_PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(id="anthropic",  name="Anthropic",    api_type="anthropic", env_var="ANTHROPIC_API_KEY",  base_url=None,                                         default_model="claude-sonnet-4-20250514"),
    ProviderInfo(id="google",     name="Google Gemini",api_type="google",    env_var="GEMINI_API_KEY",     base_url=None,                                         default_model="gemini-2.0-flash"),
    ProviderInfo(id="google-vertex", name="Vertex AI", api_type="google",    env_var="GOOGLE_CLOUD_API_KEY",base_url=None,                                       default_model="gemini-2.0-flash",
                  extra_env_vars={"GOOGLE_CLOUD_PROJECT": "GCP Project", "GOOGLE_CLOUD_LOCATION": "GCP Location"}),
    ProviderInfo(id="amazon-bedrock", name="Bedrock",  api_type="bedrock",   env_var="",                    base_url=None,                                         default_model="anthropic.claude-sonnet-4-20250514"),
]

ALL_PROVIDERS: list[ProviderInfo] = OPENAI_COMPAT_PROVIDERS + NON_OPENAI_PROVIDERS

# ---------------------------------------------------------------------------
# Provider registry — pi-ai's Models collection equivalent
# ---------------------------------------------------------------------------

_PROVIDER_MAP: dict[str, ProviderInfo] = {p.id: p for p in ALL_PROVIDERS}


def get_provider(provider_id: str) -> ProviderInfo | None:
    return _PROVIDER_MAP.get(provider_id)


def get_configured_providers() -> list[ProviderInfo]:
    """Return all providers that have their API key(s) set. (pi-ai's getAvailable)"""
    return [p for p in ALL_PROVIDERS if p.is_configured()]


def get_llm_models(provider_id: str | None = None) -> list[dict[str, Any]]:
    """Return known model info per provider. (pi-ai's getModels)"""
    if provider_id:
        p = get_provider(provider_id)
        if not p:
            return []
        return [{"provider": p.id, "name": p.name, "api_type": p.api_type, "default_model": p.default_model, "configured": p.is_configured()}]
    return [
        {"provider": p.id, "name": p.name, "api_type": p.api_type, "default_model": p.default_model, "configured": p.is_configured()}
        for p in ALL_PROVIDERS
    ]


# ---------------------------------------------------------------------------
# Factory — returns a langchain chat model (pi-ai's Models.stream / complete)
# ---------------------------------------------------------------------------

def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    """
    Return a langchain chat model for the given provider.

    Auto-detects the first configured provider when none is given.
    Falls back to the project's default LLM_PROVIDER setting.

    This is the pi-ai equivalent of ``models.stream(model, context)`` —
    but returns a synchronous langchain object for the current usage pattern.
    """
    # Resolve provider
    provider = provider or (settings.LLM_PROVIDER or "").strip().lower() or None
    if not provider or provider not in _PROVIDER_MAP:
        configured = get_configured_providers()
        if not configured:
            log.warning("No LLM provider is configured. Set at least one API key (e.g. OPENAI_API_KEY).")
            # Last-resort fallback: try to build whatever ChatOpenAI from settings
            return _build_openai_compat(settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL, model=model or "gpt-4o-mini", temperature=temperature, max_tokens=max_tokens, **kwargs)
        provider = configured[0].id
        log.info("Auto-detected provider: %s (%s)", provider, configured[0].name)

    info = _PROVIDER_MAP[provider]
    if not info.is_configured():
        log.warning("Provider '%s' is not configured (missing %s). Falling back to default.", info.id, info.env_var)
        return _build_openai_compat(settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL, model=model or "gpt-4o-mini", temperature=temperature, max_tokens=max_tokens, **kwargs)

    effective_model = model or info.default_model or _default_for(info)
    temperature = temperature if temperature is not None else 0.3
    effective_max_tokens = max_tokens or 4096

    builders = {
        "openai": _build_openai_compat,
        "anthropic": _build_anthropic,
        "google": _build_google,
        "mistral": _build_mistral,
        "bedrock": _build_bedrock,
    }
    builder = builders.get(info.api_type, _build_openai_compat)
    return builder(info, model=effective_model, temperature=temperature, max_tokens=effective_max_tokens, **kwargs)


# ---------------------------------------------------------------------------
# Backwards-compatible alias
# ---------------------------------------------------------------------------

def get_chat_openai(**overrides) -> Any:
    """
    Legacy alias — returns a ChatOpenAI-like instance.
    Now routes through get_llm() for full multi-provider support.
    """
    model = overrides.pop("model", None)
    temperature = overrides.pop("temperature", None)
    max_tokens = overrides.pop("max_tokens", None)
    provider = (settings.LLM_PROVIDER or "").strip().lower() or None
    # Tailor/parser historically pass DEFAULT_*_MODEL (often gpt-*). When the
    # active provider is MiMo/Xiaomi, ignore incompatible OpenAI model names.
    if provider in {"mimo", "xiaomi"} and model and (
        model.startswith(("gpt-", "o1", "o3", "chatgpt")) or model in {"gpt-5.5"}
    ):
        model = None
    return get_llm(provider=provider, model=model, temperature=temperature, max_tokens=max_tokens, **overrides)


# ---------------------------------------------------------------------------
# Protocol-specific builders
# ---------------------------------------------------------------------------

def _default_for(info: ProviderInfo) -> str:
    defaults = {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-sonnet-4-20250514",
        "google": "gemini-2.0-flash",
        "mistral": "open-mistral-nemo",
        "bedrock": "anthropic.claude-sonnet-4-20250514",
    }
    return defaults.get(info.api_type, "gpt-4o-mini")


def _build_openai_compat(
    info_or_key: ProviderInfo | str,
    *,
    base_url: str | None = None,
    model: str = "gpt-4o-mini",
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    from langchain_openai import ChatOpenAI

    if isinstance(info_or_key, ProviderInfo):
        api_key = info_or_key.api_key()
        effective_base_url = info_or_key.effective_base_url or base_url
    else:
        api_key = info_or_key
        effective_base_url = base_url

    params: dict[str, Any] = {
        "model": model,
        "temperature": temperature if temperature is not None else 0.3,
        "max_tokens": max_tokens or 4096,
        "api_key": api_key,
        **kwargs,
    }
    if effective_base_url:
        params["base_url"] = effective_base_url
    return ChatOpenAI(**params)


def _build_anthropic(
    info: ProviderInfo,
    *,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        temperature=temperature if temperature is not None else 0.3,
        max_tokens=max_tokens or 4096,
        api_key=info.api_key(),
        **kwargs,
    )


def _build_google(
    info: ProviderInfo,
    *,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    api_key = info.api_key()
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model,
            temperature=temperature if temperature is not None else 0.3,
            max_output_tokens=max_tokens or 4096,
            google_api_key=api_key,
            **kwargs,
        )
    except ImportError:
        log.warning("langchain-google-genai not installed. Falling back to OpenAI-compatible endpoint.")
        return _build_openai_compat(
            api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


def _build_mistral(
    info: ProviderInfo,
    *,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    api_key = info.api_key()
    try:
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(
            model=model,
            temperature=temperature if temperature is not None else 0.3,
            max_tokens=max_tokens or 4096,
            api_key=api_key,
            **kwargs,
        )
    except ImportError:
        log.warning("langchain-mistralai not installed. Falling back to OpenAI-compatible endpoint.")
        return _build_openai_compat(
            api_key,
            base_url=info.effective_base_url or "https://api.mistral.ai/v1",
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )


def _build_bedrock(
    info: ProviderInfo,
    *,
    model: str,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    try:
        from langchain_aws import ChatBedrockConverse
        return ChatBedrockConverse(
            model=model,
            temperature=temperature if temperature is not None else 0.3,
            max_tokens=max_tokens or 4096,
            **kwargs,
        )
    except ImportError:
        log.warning("langchain-aws not installed. Cannot use Bedrock directly.")
        raise
