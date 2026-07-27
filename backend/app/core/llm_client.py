"""
Unified LLM client factory.

Auto-detects provider from LLM_PROVIDER env var and returns a properly
configured ChatOpenAI (OpenAI-compatible) instance.

Providers:
  openai  -> uses OPENAI_BASE_URL + OPENAI_API_KEY from settings
  gemini  -> uses Gemini OpenAI-compat endpoint + GEMINI_API_KEY
  zhipu   -> uses Zhipu/GLM API + BIGMODEL_API_KEY

Usage:
  from app.core.llm_client import get_chat_openai
  llm = get_chat_openai(model="gpt-5.5", temperature=0.3)
  response = llm.invoke([("human", "Hello")])
"""

import logging

from langchain_openai import ChatOpenAI

from app.config import settings

log = logging.getLogger(__name__)


def _get_provider_config(provider: str) -> dict:
    configs = {
        "openai": {
            "base_url": settings.OPENAI_BASE_URL or None,
            "api_key": settings.OPENAI_API_KEY,
            "default_model": settings.DEFAULT_TAILOR_MODEL or "gpt-4o-mini",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
            "api_key": settings.GEMINI_API_KEY,
            "default_model": "gemini-2.0-flash",
        },
        "zhipu": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": settings.BIGMODEL_API_KEY,
            "default_model": "glm-4v-flash",
        },
    }
    if provider not in configs:
        log.warning("Unknown LLM_PROVIDER '%s', falling back to 'openai'", provider)
        return configs["openai"]
    return configs[provider]


def get_chat_openai(**overrides) -> ChatOpenAI:
    provider = (settings.LLM_PROVIDER or "openai").strip().lower()
    cfg = _get_provider_config(provider)

    kwargs = {
        "model": overrides.pop("model", cfg["default_model"]),
        "api_key": cfg["api_key"],
        "temperature": overrides.pop("temperature", 0.3),
    }
    if cfg["base_url"]:
        kwargs["base_url"] = cfg["base_url"]
    kwargs.update(overrides)

    log.debug("LLM provider=%s model=%s base_url=%s", provider, kwargs["model"], kwargs.get("base_url", "(default)"))
    return ChatOpenAI(**kwargs)
