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

    def api_key(self) -> str | None:
        """Resolve the API key from env (pi-ai's getEnvApiKey)."""
        key = self._get_env(self.env_var)
        if key:
            return key
        # Zhipu / BigModel aliases
        if self.id in {"zhipu", "bigmodel"}:
            return self._get_env("ZHIPU_API_KEY") or self._get_env("BIGMODEL_API_KEY")
        # Xiaomi MiMo aliases
        if self.id in {"xiaomi", "mimo"}:
            return self._get_env("XIAOMI_API_KEY") or self._get_env("MIMO_API_KEY")
        return None

    def is_configured(self) -> bool:
        """Check whether the essential API key env var is set (pi-ai's findEnvKeys)."""
        if self.api_key():
            return True
        # Some providers have ambient auth (Bedrock, Vertex) — check extra hints
        if self.id == "amazon-bedrock":
            return bool(self._get_env("AWS_PROFILE") or self._get_env("AWS_ACCESS_KEY_ID"))
        if self.id == "google-vertex":
            return bool(self._get_env("GOOGLE_CLOUD_API_KEY") or (
                self._get_env("GOOGLE_CLOUD_PROJECT") and self._get_env("GOOGLE_CLOUD_LOCATION")
            ))
        return False

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
    ProviderInfo(id="openai",         name="OpenAI",              api_type="openai",   env_var="OPENAI_API_KEY",                      default_model="gemini-3.5-flash",
                  base_url_env="OPENAI_BASE_URL"),
    ProviderInfo(id="zhipu",          name="Zhipu (BigModel)",    api_type="openai",   env_var="BIGMODEL_API_KEY", base_url="https://open.bigmodel.cn/api/paas/v4", default_model="glm-4-flash"),
    ProviderInfo(id="bigmodel",       name="BigModel",            api_type="openai",   env_var="BIGMODEL_API_KEY", base_url="https://open.bigmodel.cn/api/paas/v4", default_model="glm-4-flash"),
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
    ProviderInfo(id="xiaomi",         name="Xiaomi MiMo",         api_type="openai",   env_var="XIAOMI_API_KEY",      base_url="https://api.xiaomimimo.com/v1",               default_model="mimo-v2.5"),
    ProviderInfo(id="mimo",           name="Xiaomi MiMo",         api_type="openai",   env_var="MIMO_API_KEY",        base_url="https://api.xiaomimimo.com/v1",               default_model="mimo-v2.5"),
    ProviderInfo(id="cloudflare",     name="Cloudflare Workers AI",api_type="openai",  env_var="CLOUDFLARE_API_KEY",  base_url=None,                                            default_model="@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                  extra_env_vars={"CLOUDFLARE_ACCOUNT_ID": "Cloudflare Account ID"}),
    ProviderInfo(id="ant-ling",       name="Ant Ling",            api_type="openai",   env_var="ANT_LING_API_KEY",    base_url="https://api.antling.ai/v1",                    default_model="ant-ling-v1"),
    ProviderInfo(id="kimi-coding",    name="Kimi For Coding",     api_type="openai",   env_var="KIMI_API_KEY",        base_url="https://api.moonshot.cn/v1",                   default_model="kimi-coding"),
    ProviderInfo(id="qwen-token",     name="Qwen Token Plan",     api_type="openai",   env_var="QWEN_TOKEN_PLAN_API_KEY", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", default_model="qwen-plus"),
    ProviderInfo(id="radius",         name="Radius",              api_type="openai",   env_var="RADIUS_API_KEY",      base_url="https://api.radius.ai/v1",                     default_model="radius-default"),
    ProviderInfo(id="yiling-glm",     name="GLM-5.2 (yiling)",    api_type="openai",   env_var="YILING_GLM_API_KEY",  base_url="https://router.c.yiling.top/v1",               default_model="glm-5.2"),
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
# Runtime preference + last successful usage (for UI)
# ---------------------------------------------------------------------------

_RUNTIME_PREFERRED: str | None = None  # overrides settings.LLM_PROVIDER when set
_RUNTIME_FAILOVER: bool | None = None  # overrides settings.LLM_FAILOVER when set
_LAST_USAGE: dict[str, str | None] = {"provider": None, "model": None}


def get_runtime_preference() -> dict[str, Any]:
    preferred = _RUNTIME_PREFERRED
    if preferred is None:
        preferred = (settings.LLM_PROVIDER or "").strip().lower() or None
    failover = _RUNTIME_FAILOVER
    if failover is None:
        raw = getattr(settings, "LLM_FAILOVER", True)
        failover = bool(raw) if not isinstance(raw, str) else str(raw).lower() not in {"0", "false", "no", "off"}
    return {
        "preferred_provider": preferred,
        "failover": failover,
        "last_provider": _LAST_USAGE.get("provider"),
        "last_model": _LAST_USAGE.get("model"),
    }


def set_runtime_preference(
    *,
    provider: str | None = None,
    failover: bool | None = None,
) -> dict[str, Any]:
    global _RUNTIME_PREFERRED, _RUNTIME_FAILOVER
    if provider is not None:
        pid = provider.strip().lower()
        if pid in {"", "auto", "default"}:
            _RUNTIME_PREFERRED = None
        elif pid not in _PROVIDER_MAP:
            raise ValueError(f"Unknown provider: {provider}")
        else:
            info = _PROVIDER_MAP[pid]
            if not info.is_configured():
                raise ValueError(f"Provider '{pid}' has no API key configured")
            _RUNTIME_PREFERRED = pid
    if failover is not None:
        _RUNTIME_FAILOVER = bool(failover)
    return get_runtime_preference()


def record_llm_usage(provider: str | None, model: str | None) -> None:
    if provider:
        _LAST_USAGE["provider"] = provider
    if model:
        _LAST_USAGE["model"] = model


def describe_llm_status() -> dict[str, Any]:
    prefs = get_runtime_preference()
    preferred = prefs["preferred_provider"]
    configured = _dedupe_providers(get_configured_providers())
    models = []
    for p in configured:
        cooled = _provider_cooled_down(p.id)
        models.append(
            {
                "id": p.id,
                "name": p.name,
                "default_model": p.default_model or _default_for(p),
                "configured": True,
                "preferred": p.id == preferred,
                "cooled_down": cooled,
            }
        )
    # Also list unconfigured known providers (collapsed) for UI search — optional short list
    known_extra = []
    configured_ids = {m["id"] for m in models}
    for p in ALL_PROVIDERS:
        if p.id in configured_ids:
            continue
        # skip aliases of already-listed endpoints
        if p.id in {"bigmodel", "mimo"}:
            continue
        known_extra.append(
            {
                "id": p.id,
                "name": p.name,
                "default_model": p.default_model or _default_for(p),
                "configured": False,
                "preferred": False,
                "cooled_down": False,
            }
        )
    active_provider = prefs["last_provider"] or preferred
    active_model = prefs["last_model"]
    if not active_model and active_provider and active_provider in _PROVIDER_MAP:
        info = _PROVIDER_MAP[active_provider]
        active_model = info.default_model or _default_for(info)
    active_name = None
    if active_provider and active_provider in _PROVIDER_MAP:
        active_name = _PROVIDER_MAP[active_provider].name
    return {
        **prefs,
        "active_provider": active_provider,
        "active_provider_name": active_name,
        "active_model": active_model,
        "configured": models,
        "available": known_extra,
    }


# ---------------------------------------------------------------------------
# Failover — try configured providers until one responds
# ---------------------------------------------------------------------------

# provider_id -> unix timestamp until which we skip (after recent failure)
_PROVIDER_COOLDOWN: dict[str, float] = {}
_COOLDOWN_SECONDS = 45

_RETRYABLE_MARKERS = (
    "503",
    "502",
    "504",
    "429",
    "service temporarily unavailable",
    "rate limit",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "overloaded",
    "capacity",
    "bad gateway",
    "gateway timeout",
    "api_error",
)


def _is_retryable_llm_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(m in text for m in _RETRYABLE_MARKERS):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    try:
        if int(status) in {408, 429, 500, 502, 503, 504}:
            return True
    except (TypeError, ValueError):
        pass
    # openai / httpx nested
    body = getattr(exc, "body", None) or getattr(exc, "response", None)
    if body is not None and any(m in str(body).lower() for m in _RETRYABLE_MARKERS):
        return True
    return False


def _provider_cooled_down(provider_id: str) -> bool:
    import time

    until = _PROVIDER_COOLDOWN.get(provider_id) or 0
    return time.time() < until


def _mark_provider_cooldown(provider_id: str) -> None:
    import time

    _PROVIDER_COOLDOWN[provider_id] = time.time() + _COOLDOWN_SECONDS


def _clear_provider_cooldown(provider_id: str) -> None:
    _PROVIDER_COOLDOWN.pop(provider_id, None)


def _dedupe_providers(providers: list[ProviderInfo]) -> list[ProviderInfo]:
    """Skip aliases that share the same endpoint + API key (e.g. zhipu/bigmodel, xiaomi/mimo)."""
    seen: set[tuple[str | None, str | None]] = set()
    out: list[ProviderInfo] = []
    for p in providers:
        key = (p.effective_base_url or p.base_url, (p.api_key() or "")[:16] or p.env_var)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _failover_provider_order(preferred: str | None) -> list[ProviderInfo]:
    configured = _dedupe_providers(get_configured_providers())
    if not configured:
        return []
    ordered: list[ProviderInfo] = []
    if preferred:
        for p in configured:
            if p.id == preferred:
                ordered.append(p)
                break
    for p in configured:
        if not ordered or p.id != ordered[0].id:
            ordered.append(p)
    return ordered


def _build_llm_for_provider(
    info: ProviderInfo,
    *,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
    use_requested_model: bool,
    **kwargs: Any,
):
    if use_requested_model and model:
        effective_model = model
    else:
        effective_model = info.default_model or _default_for(info)
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
    return builder(
        info,
        model=effective_model,
        temperature=temperature,
        max_tokens=effective_max_tokens,
        **kwargs,
    ), effective_model


class FailoverChatModel:
    """
    Drop-in chat model: try preferred provider, then other configured ones.

    On 503/429/timeouts, cools down the failing provider briefly and continues.
    Backup providers always use their own default model (never e.g. glm-* on Gemini).
    """

    def __init__(
        self,
        *,
        preferred: str | None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enable_failover: bool = True,
        **kwargs: Any,
    ):
        self.preferred = preferred
        self.requested_model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.enable_failover = enable_failover
        self.kwargs = kwargs
        self.last_provider: str | None = None
        self.last_model: str | None = None

    def _candidates(self) -> list[tuple[ProviderInfo, Any, str]]:
        order = _failover_provider_order(self.preferred)
        if not order:
            # Last resort: raw OpenAI settings
            llm = _build_openai_compat(
                settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL or None,
                model=self.requested_model or "gpt-4o-mini",
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                **self.kwargs,
            )
            dummy = ProviderInfo(
                id="openai",
                name="OpenAI",
                api_type="openai",
                env_var="OPENAI_API_KEY",
                default_model="gpt-4o-mini",
            )
            return [(dummy, llm, self.requested_model or "gpt-4o-mini")]

        if not self.enable_failover:
            order = order[:1]

        out: list[tuple[ProviderInfo, Any, str]] = []
        for i, info in enumerate(order):
            use_req = i == 0 and bool(self.preferred and info.id == self.preferred)
            try:
                llm, mid = _build_llm_for_provider(
                    info,
                    model=self.requested_model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    use_requested_model=use_req,
                    **self.kwargs,
                )
            except Exception as exc:
                log.warning("Skip building LLM for %s: %s", info.id, exc)
                continue
            out.append((info, llm, mid))
        return out

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        errors: list[tuple[str, BaseException]] = []
        for info, llm, mid in self._candidates():
            if _provider_cooled_down(info.id):
                log.info("LLM skip cooled-down provider: %s", info.id)
                continue
            try:
                result = llm.invoke(messages, **kwargs)
                self.last_provider = info.id
                self.last_model = mid
                record_llm_usage(info.id, mid)
                _clear_provider_cooldown(info.id)
                if self.preferred and info.id != self.preferred:
                    log.warning(
                        "LLM failover OK: preferred=%s → using=%s model=%s",
                        self.preferred,
                        info.id,
                        mid,
                    )
                return result
            except Exception as exc:
                if not _is_retryable_llm_error(exc) or not self.enable_failover:
                    raise
                _mark_provider_cooldown(info.id)
                errors.append((info.id, exc))
                log.warning("LLM provider %s failed (%s); trying next", info.id, exc)
        if not errors:
            raise RuntimeError("No LLM providers available (none configured or all cooled down).")
        detail = "; ".join(f"{pid}: {err}" for pid, err in errors)
        raise RuntimeError(f"All LLM providers failed. {detail}") from errors[-1][1]

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        errors: list[tuple[str, BaseException]] = []
        for info, llm, mid in self._candidates():
            if _provider_cooled_down(info.id):
                log.info("LLM skip cooled-down provider: %s", info.id)
                continue
            try:
                result = await llm.ainvoke(messages, **kwargs)
                self.last_provider = info.id
                self.last_model = mid
                record_llm_usage(info.id, mid)
                _clear_provider_cooldown(info.id)
                if self.preferred and info.id != self.preferred:
                    log.warning(
                        "LLM failover OK: preferred=%s → using=%s model=%s",
                        self.preferred,
                        info.id,
                        mid,
                    )
                return result
            except Exception as exc:
                if not _is_retryable_llm_error(exc) or not self.enable_failover:
                    raise
                _mark_provider_cooldown(info.id)
                errors.append((info.id, exc))
                log.warning("LLM provider %s failed (%s); trying next", info.id, exc)
        if not errors:
            raise RuntimeError("No LLM providers available (none configured or all cooled down).")
        detail = "; ".join(f"{pid}: {err}" for pid, err in errors)
        raise RuntimeError(f"All LLM providers failed. {detail}") from errors[-1][1]

    def bind_tools(self, tools: Any, **kwargs: Any) -> _ToolsBoundFailover:
        """Bind tools onto each failover candidate (OpenAI-compatible function calling)."""
        return _ToolsBoundFailover(self, tools, **kwargs)


class _ToolsBoundFailover:
    """Failover wrapper that calls ``llm.bind_tools(...)`` per provider attempt."""

    def __init__(self, failover: FailoverChatModel, tools: Any, **bind_kwargs: Any):
        self._failover = failover
        self._tools = tools
        self._bind_kwargs = bind_kwargs

    @property
    def last_provider(self) -> str | None:
        return self._failover.last_provider

    @property
    def last_model(self) -> str | None:
        return self._failover.last_model

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        errors: list[tuple[str, BaseException]] = []
        for info, llm, mid in self._failover._candidates():
            if _provider_cooled_down(info.id):
                continue
            try:
                bound = llm.bind_tools(self._tools, **self._bind_kwargs)
                result = bound.invoke(messages, **kwargs)
                self._failover.last_provider = info.id
                self._failover.last_model = mid
                record_llm_usage(info.id, mid)
                _clear_provider_cooldown(info.id)
                return result
            except Exception as exc:
                if not _is_retryable_llm_error(exc) or not self._failover.enable_failover:
                    raise
                _mark_provider_cooldown(info.id)
                errors.append((info.id, exc))
                log.warning("LLM bind_tools provider %s failed (%s); trying next", info.id, exc)
        if not errors:
            raise RuntimeError("No LLM providers available for bind_tools.")
        detail = "; ".join(f"{pid}: {err}" for pid, err in errors)
        raise RuntimeError(f"All LLM providers failed (bind_tools). {detail}") from errors[-1][1]

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        errors: list[tuple[str, BaseException]] = []
        for info, llm, mid in self._failover._candidates():
            if _provider_cooled_down(info.id):
                continue
            try:
                bound = llm.bind_tools(self._tools, **self._bind_kwargs)
                result = await bound.ainvoke(messages, **kwargs)
                self._failover.last_provider = info.id
                self._failover.last_model = mid
                record_llm_usage(info.id, mid)
                _clear_provider_cooldown(info.id)
                return result
            except Exception as exc:
                if not _is_retryable_llm_error(exc) or not self._failover.enable_failover:
                    raise
                _mark_provider_cooldown(info.id)
                errors.append((info.id, exc))
                log.warning("LLM bind_tools provider %s failed (%s); trying next", info.id, exc)
        if not errors:
            raise RuntimeError("No LLM providers available for bind_tools.")
        detail = "; ".join(f"{pid}: {err}" for pid, err in errors)
        raise RuntimeError(f"All LLM providers failed (bind_tools). {detail}") from errors[-1][1]


# ---------------------------------------------------------------------------
# Factory — returns a langchain chat model (pi-ai's Models.stream / complete)
# ---------------------------------------------------------------------------

def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    *,
    failover: bool | None = None,
    **kwargs: Any,
):
    """
    Return a chat model with multi-provider failover.

    Preferred provider: explicit ``provider`` arg, else runtime UI preference,
    else ``LLM_PROVIDER``, else first configured key.
    """
    prefs = get_runtime_preference()
    preferred = (
        provider
        or prefs.get("preferred_provider")
        or (settings.LLM_PROVIDER or "").strip().lower()
        or None
    )
    if preferred and preferred not in _PROVIDER_MAP:
        log.warning("Unknown LLM_PROVIDER=%s; will auto-pick from configured keys.", preferred)
        preferred = None
    if preferred and not _PROVIDER_MAP[preferred].is_configured():
        log.warning(
            "Preferred provider '%s' has no API key; will fail over to other configured providers.",
            preferred,
        )

    enable = failover
    if enable is None:
        enable = bool(prefs.get("failover", True))

    return FailoverChatModel(
        preferred=preferred,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_failover=enable,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Backwards-compatible alias
# ---------------------------------------------------------------------------

def get_chat_openai(**overrides) -> Any:
    """
    Legacy alias — returns a chat model (with failover by default).
    Now routes through get_llm() for full multi-provider support.
    """
    model = overrides.pop("model", None)
    temperature = overrides.pop("temperature", None)
    max_tokens = overrides.pop("max_tokens", None)
    failover = overrides.pop("failover", None)
    return get_llm(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        failover=failover,
        **overrides,
    )


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
    # Gateways (MiMo / Gemini flash / GLM) often bill "thinking" into completion
    # tokens and truncate `content` when max_tokens is modest. Disable by default.
    model_l = (model or "").lower()
    provider_id = info_or_key.id if isinstance(info_or_key, ProviderInfo) else ""
    needs_no_think = provider_id in {"xiaomi", "mimo", "yiling-glm", "openai"} or any(
        model_l.startswith(p) for p in ("gemini", "glm", "mimo")
    )
    if needs_no_think:
        extra = dict(params.get("extra_body") or {})
        extra.setdefault("thinking", {"type": "disabled"})
        params["extra_body"] = extra
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
