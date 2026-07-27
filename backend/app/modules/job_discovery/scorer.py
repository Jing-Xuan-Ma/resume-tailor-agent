"""Job matching score utilities."""

import re


def tokenize(text: str) -> set[str]:
    stop = {"and", "the", "for", "with", "you", "our", "job", "role", "team", "this", "that", "are", "not", "have", "from", "your", "will", "all", "can", "has", "its", "also", "been", "than", "what", "who", "about", "their", "they", "was", "were", "one", "been", "being", "very", "just", "some", "each", "which"}
    return {token for token in re.findall(r"[a-zA-Z][a-zA-Z0-9+#.-]{2,}", text.lower()) if token not in stop}


def score_job(parsed: dict, query: str, resume_text: str = "") -> float:
    jd_text = " ".join(
        str(value)
        for value in [
            parsed.get("title", ""),
            *(parsed.get("required_skills") or []),
            *(parsed.get("preferred_skills") or []),
            *(parsed.get("ats_keywords") or []),
            *(parsed.get("key_responsibilities") or []),
        ]
    )
    jd_tokens = tokenize(jd_text)
    query_tokens = tokenize(query)
    resume_tokens = tokenize(resume_text)

    query_overlap = len(query_tokens & jd_tokens) / max(1, len(query_tokens))
    overlap_count = len(resume_tokens & jd_tokens)
    resume_overlap = overlap_count / max(1, min(len(resume_tokens), max(len(jd_tokens), 1))) if resume_tokens else 0
    score = 30 + 45 * query_overlap + 25 * resume_overlap
    return round(min(score, 100), 1) if score > 0 else round(score, 1)
