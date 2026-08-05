"""Translate JD bullet segments EN→zh for bilingual JD panel."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

_CACHE: dict[str, str] = {}
_MAX_CACHE = 2000

# Lightweight offline gloss for common DA JD phrases (API/LLM may be unreachable).
_PHRASE_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(\d+\+?)\s*years?\s+of\s+(?:experience\s+)?(?:in|with)?\s*", re.I), r"\1年以上"),
    (re.compile(r"\byears?\s+of\s+experience\b", re.I), "年经验"),
    (re.compile(r"\bexperience\s+with\b", re.I), "具备以下经验："),
    (re.compile(r"\bexperience\s+in\b", re.I), "具备以下方面经验："),
    (re.compile(r"\bstrong\s+analytical\b", re.I), "较强的分析"),
    (re.compile(r"\bcommunication\s+skills?\b", re.I), "沟通能力"),
    (re.compile(r"\bproblem[\s-]solving\b", re.I), "解决问题"),
    (re.compile(r"\bstakeholders?\b", re.I), "业务方/利益相关方"),
    (re.compile(r"\bdashboards?\b", re.I), "仪表盘"),
    (re.compile(r"\bdata\s+visualization\b", re.I), "数据可视化"),
    (re.compile(r"\bdata\s+analysis\b", re.I), "数据分析"),
    (re.compile(r"\bbusiness\s+intelligence\b", re.I), "商业智能"),
    (re.compile(r"\brequirements?\b", re.I), "要求"),
    (re.compile(r"\bpreferred\b", re.I), "优先"),
    (re.compile(r"\bBachelor'?s?\s+degree\b", re.I), "学士学位"),
    (re.compile(r"\bMaster'?s?\s+degree\b", re.I), "硕士学位"),
    (re.compile(r"\bremote\b", re.I), "远程"),
    (re.compile(r"\bhybrid\b", re.I), "混合办公"),
    (re.compile(r"\bfull[\s-]time\b", re.I), "全职"),
    (re.compile(r"\bcross[\s-]functional\b", re.I), "跨职能"),
    (re.compile(r"\bA/?B\s+test(ing)?\b", re.I), "A/B 测试"),
    (re.compile(r"\bmachine\s+learning\b", re.I), "机器学习"),
    (re.compile(r"\bwork\s+with\b", re.I), "与…协作"),
    (re.compile(r"\bability\s+to\b", re.I), "能够"),
    (re.compile(r"\bproficien(t|cy)\s+in\b", re.I), "熟练掌握"),
    (re.compile(r"\bfamiliar(ity)?\s+with\b", re.I), "熟悉"),
    (re.compile(r"\bknowledge\s+of\b", re.I), "了解"),
    (re.compile(r"\bexperience\b", re.I), "经验"),
]


def _local_gloss(text: str) -> str:
    """Best-effort bilingual gloss when remote translators are offline."""
    out = text
    hits = 0
    for pat, zh in _PHRASE_MAP:
        nxt, n = pat.subn(zh, out)
        if n:
            hits += n
            out = nxt
    if hits == 0:
        return f"（译）{text}"
    return out


def _cache_get(text: str) -> str | None:
    return _CACHE.get(text)


def _cache_set(text: str, zh: str) -> None:
    if len(_CACHE) >= _MAX_CACHE:
        for k in list(_CACHE.keys())[:200]:
            _CACHE.pop(k, None)
    _CACHE[text] = zh


async def _mymemory_one(text: str) -> str | None:
    q = text.strip()
    if not q:
        return ""
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.get(
                "https://api.mymemory.translated.net/get",
                params={"q": q[:450], "langpair": "en|zh-CN"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            out = (data.get("responseData") or {}).get("translatedText") or ""
            out = str(out).strip()
            if not out or out.lower() == q.lower():
                return None
            if "MYMEMORY WARNING" in out.upper():
                return None
            return out
    except Exception as exc:
        log.debug("mymemory failed: %s", exc)
        return None


async def _llm_batch(texts: list[str]) -> list[str] | None:
    try:
        from app.core.llm_client import get_chat_openai
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception as exc:
        log.debug("llm import failed: %s", exc)
        return None

    payload = [{"i": i, "text": t} for i, t in enumerate(texts)]
    system = (
        "You translate English job-description bullets to Simplified Chinese. "
        "Keep tool/product names (SQL, Tableau, Python, AWS, etc.) in English. "
        "Return ONLY a JSON array of objects: [{\"i\":0,\"zh\":\"...\"}, ...]. "
        "Same length and order as input. No markdown."
    )
    try:
        llm = get_chat_openai(temperature=0.1)
        resp = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
            ]
        )
        raw = str(getattr(resp, "content", "") or "").strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        by_i = {
            int(item["i"]): str(item.get("zh") or "").strip()
            for item in data
            if isinstance(item, dict) and "i" in item
        }
        out = [by_i.get(i, "") for i in range(len(texts))]
        if sum(1 for x in out if x) < max(1, len(texts) // 2):
            return None
        return out
    except Exception as exc:
        log.warning("llm translate batch failed: %s", exc)
        return None


async def translate_segments(texts: list[str], *, target_lang: str = "zh-CN") -> dict[str, Any]:
    """Return {translations: [{source, translated}], provider}."""
    cleaned = [str(t or "").strip() for t in texts][:40]
    results: list[str | None] = [None] * len(cleaned)
    pending_idx: list[int] = []

    for i, t in enumerate(cleaned):
        if not t:
            results[i] = ""
            continue
        hit = _cache_get(t)
        if hit is not None:
            results[i] = hit
        else:
            pending_idx.append(i)

    provider = "cache"
    if pending_idx:
        pending_texts = [cleaned[i] for i in pending_idx]
        llm_out = await _llm_batch(pending_texts) if target_lang.startswith("zh") else None
        if llm_out and len(llm_out) == len(pending_texts):
            provider = "llm"
            for j, i in enumerate(pending_idx):
                zh = llm_out[j] or pending_texts[j]
                results[i] = zh
                _cache_set(cleaned[i], zh)
        else:
            provider = "mymemory"
            any_remote = False
            for i in pending_idx:
                zh = await _mymemory_one(cleaned[i])
                if zh is None:
                    zh = _local_gloss(cleaned[i])
                else:
                    any_remote = True
                results[i] = zh
                _cache_set(cleaned[i], zh)
            if not any_remote:
                provider = "local_gloss"

    return {
        "translations": [
            {"source": cleaned[i], "translated": results[i] or ""}
            for i in range(len(cleaned))
        ],
        "provider": provider,
        "target_lang": target_lang,
    }
