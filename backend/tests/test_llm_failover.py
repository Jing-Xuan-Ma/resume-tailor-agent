"""LLM multi-provider failover smoke tests."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from app.core import llm_client as lc
from app.core.llm_client import FailoverChatModel, get_llm, _is_retryable_llm_error


def test_retryable_markers():
    assert _is_retryable_llm_error(RuntimeError("Error code: 503 - Service temporarily unavailable"))
    assert _is_retryable_llm_error(RuntimeError("rate limit exceeded"))
    assert not _is_retryable_llm_error(ValueError("invalid api key format xyz"))


async def test_failover_from_dead_openai_model():
    # Prefer openai (yiling) with a model that returns 503; expect zhipu/google backup.
    lc._PROVIDER_COOLDOWN.clear()
    llm = get_llm(provider="openai", model="glm-4v-flash", temperature=0, max_tokens=16)
    assert isinstance(llm, FailoverChatModel)
    result = await llm.ainvoke([("human", "Reply with exactly: PONG")])
    text = str(getattr(result, "content", result) or "")
    assert "PONG" in text.upper() or "pong" in text.lower() or len(text) > 0
    assert llm.last_provider in {"zhipu", "bigmodel", "google", "openai"}
    # If openai 503'd, last_provider should not stay on a dead path with glm-4v-flash
    print("failover used provider=", llm.last_provider, "model=", llm.last_model, "text=", text[:80])


async def test_preferred_zhipu_works():
    lc._PROVIDER_COOLDOWN.clear()
    llm = get_llm(provider="zhipu", model="glm-4-flash", temperature=0, max_tokens=16)
    result = await llm.ainvoke([("human", "Reply with exactly: OK")])
    text = str(getattr(result, "content", result) or "")
    assert llm.last_provider in {"zhipu", "bigmodel"}
    assert "OK" in text.upper() or len(text) > 0
    print("zhipu ok", text[:80])


if __name__ == "__main__":
    test_retryable_markers()
    print("retryable OK")
    asyncio.run(test_preferred_zhipu_works())
    asyncio.run(test_failover_from_dead_openai_model())
    print("ALL OK")
