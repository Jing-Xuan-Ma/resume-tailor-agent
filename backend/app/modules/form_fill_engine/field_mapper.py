"""Profile ↔ form field mapping (Tier 1 rules + Tier 2 semantic fallback)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.modules.form_fill_engine.schemas import FieldMappingResult, InteractiveElement

# Align with canonical_profile keys; include spec aliases as sources.
FIELD_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"first\s?name|given\s?name|firstname", re.I), "first_name"),
    (re.compile(r"last\s?name|family\s?name|surname|lastname", re.I), "last_name"),
    (re.compile(r"full\s?name|your\s+name|candidate\s+name", re.I), "full_name"),
    (re.compile(r"e-?mail", re.I), "email"),
    (re.compile(r"phone|mobile|telephone|\btel\b", re.I), "phone"),
    (re.compile(r"legally?\s+authorized|work\s+authorization|authorized\s+to\s+work", re.I), "work_authorized"),
    (re.compile(r"(require|need).{0,20}sponsorship|visa\s+sponsor", re.I), "needs_sponsorship"),
    (re.compile(r"linkedin", re.I), "linkedin"),
    (re.compile(r"github", re.I), "github"),
    (re.compile(r"portfolio|personal\s+site|website(?!\s*application)", re.I), "portfolio"),
    (re.compile(r"street\s+address|mailing\s+address|\baddress\b", re.I), "address"),
    (re.compile(r"^city$|\bcity\b", re.I), "city"),
    (re.compile(r"^state$|\bstate\b|\bprovince\b", re.I), "state"),
    (re.compile(r"zip|postal", re.I), "zip_code"),
    (re.compile(r"\blocation\b", re.I), "location"),
    (re.compile(r"\bresume\b|\bcv\b", re.I), "resume_path"),
    (re.compile(r"cover\s*letter", re.I), "cover_letter_path"),
    (re.compile(r"earliest\s+start|start\s+date|available\s+to\s+start", re.I), "earliest_start"),
    (re.compile(r"salary|compensation|expected\s+pay", re.I), "salary_expectation"),
    (re.compile(r"visa\s+status|immigration", re.I), "visa_status"),
]

# Human-readable labels for Tier 2 semantic match against element labels.
PROFILE_KEY_DESCRIPTIONS: dict[str, str] = {
    "first_name": "first name given name",
    "last_name": "last name family name surname",
    "full_name": "full legal name",
    "email": "email address",
    "phone": "phone mobile telephone number",
    "work_authorized": "legally authorized to work work authorization",
    "needs_sponsorship": "require visa sponsorship",
    "linkedin": "linkedin profile url",
    "github": "github profile url",
    "portfolio": "portfolio website personal site",
    "address": "street mailing address",
    "city": "city",
    "state": "state province",
    "zip_code": "zip postal code",
    "location": "current location city",
    "resume_path": "resume cv upload",
    "cover_letter_path": "cover letter upload",
    "earliest_start": "earliest start date availability",
    "salary_expectation": "salary expectation compensation",
    "visa_status": "visa immigration status",
}

SEMANTIC_THRESHOLD = 0.55
_EMBEDDER = None
_EMBEDDER_FAILED = False


def _profile_value(profile: dict[str, Any], key: str) -> str | None:
    """Resolve value with common alias keys from apply profile / spec."""
    aliases = {
        "linkedin": ("linkedin", "linkedin_url"),
        "github": ("github", "github_url"),
        "portfolio": ("portfolio", "portfolio_url"),
        "work_authorized": ("work_authorized", "work_authorization"),
        "address": ("address", "street_address", "mailing_address"),
        "zip_code": ("zip_code", "postal", "zip"),
        "city": ("city",),
        "state": ("state",),
    }
    keys = aliases.get(key, (key,))
    for k in keys:
        v = profile.get(k)
        if v is None or v == "":
            continue
        if isinstance(v, bool):
            return "Yes" if v else "No"
        return str(v)
    return None


def _label_blob(element: InteractiveElement) -> str:
    return " ".join(
        p
        for p in [
            element.label or "",
            element.element_type or "",
            element.tag or "",
        ]
        if p
    ).strip()


def _rule_match(element: InteractiveElement, profile: dict[str, Any]) -> FieldMappingResult | None:
    blob = _label_blob(element)
    if not blob:
        return None
    # Prefer file upload for file inputs
    if (element.element_type or "").lower() == "file":
        for pattern, key in FIELD_RULES:
            if key in {"resume_path", "cover_letter_path"} and pattern.search(blob):
                val = _profile_value(profile, key)
                if val:
                    return FieldMappingResult(
                        element_index=element.index,
                        matched_profile_key=key,
                        value_to_fill=val,
                        match_method="rule",
                        confidence=0.9,
                    )
        val = _profile_value(profile, "resume_path")
        if val:
            return FieldMappingResult(
                element_index=element.index,
                matched_profile_key="resume_path",
                value_to_fill=val,
                match_method="rule",
                confidence=0.75,
            )

    for pattern, profile_key in FIELD_RULES:
        if pattern.search(blob):
            val = _profile_value(profile, profile_key)
            if val:
                return FieldMappingResult(
                    element_index=element.index,
                    matched_profile_key=profile_key,
                    value_to_fill=val,
                    match_method="rule",
                    confidence=0.9,
                )
            return FieldMappingResult(
                element_index=element.index,
                matched_profile_key=profile_key,
                value_to_fill=None,
                match_method="rule",
                confidence=0.45,
            )
    return None


def _token_similarity(a: str, b: str) -> float:
    a_l, b_l = a.lower().strip(), b.lower().strip()
    if not a_l or not b_l:
        return 0.0
    return SequenceMatcher(None, a_l, b_l).ratio()


def _get_embedder():
    """Optional sentence-transformers; falls back to SequenceMatcher."""
    global _EMBEDDER, _EMBEDDER_FAILED
    if _EMBEDDER_FAILED:
        return None
    if _EMBEDDER is not None:
        return _EMBEDDER
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _EMBEDDER = SentenceTransformer("all-MiniLM-L6-v2")
        return _EMBEDDER
    except Exception:
        _EMBEDDER_FAILED = True
        return None


def semantic_match(element: InteractiveElement, profile: dict[str, Any]) -> FieldMappingResult | None:
    label = _label_blob(element)
    if not label:
        return None

    model = _get_embedder()
    best_key: str | None = None
    best_score = 0.0

    if model is not None:
        try:
            import numpy as np  # type: ignore

            keys = [k for k in PROFILE_KEY_DESCRIPTIONS if _profile_value(profile, k)]
            if not keys:
                return None
            texts = [label] + [PROFILE_KEY_DESCRIPTIONS[k] for k in keys]
            emb = model.encode(texts, normalize_embeddings=True)
            q = emb[0]
            scores = emb[1:] @ q
            idx = int(np.argmax(scores))
            best_score = float(scores[idx])
            best_key = keys[idx]
        except Exception:
            model = None

    if model is None:
        for key, desc in PROFILE_KEY_DESCRIPTIONS.items():
            if not _profile_value(profile, key):
                continue
            score = _token_similarity(label, desc)
            # boost shared keywords
            lab_tokens = set(re.findall(r"[a-z0-9]+", label.lower()))
            desc_tokens = set(re.findall(r"[a-z0-9]+", desc.lower()))
            if lab_tokens and desc_tokens:
                jacc = len(lab_tokens & desc_tokens) / len(lab_tokens | desc_tokens)
                score = max(score, jacc)
            if score > best_score:
                best_score = score
                best_key = key

    if best_key is None or best_score < SEMANTIC_THRESHOLD:
        return None
    val = _profile_value(profile, best_key)
    return FieldMappingResult(
        element_index=element.index,
        matched_profile_key=best_key,
        value_to_fill=val,
        match_method="semantic",
        confidence=round(min(0.85, best_score), 3),
    )


def map_field(element: InteractiveElement, profile: dict[str, Any]) -> FieldMappingResult:
    hit = _rule_match(element, profile)
    if hit and hit.value_to_fill:
        return hit
    if hit and hit.matched_profile_key and not hit.value_to_fill:
        # Profile empty for matched key — still try semantic for alternatives
        pass

    semantic = semantic_match(element, profile)
    if semantic and semantic.value_to_fill:
        return semantic

    if hit:
        return hit
    return FieldMappingResult(
        element_index=element.index,
        matched_profile_key=None,
        value_to_fill=None,
        match_method="unmatched",
        confidence=0.0,
    )


def map_all_fields(
    elements: list[InteractiveElement],
    profile: dict[str, Any],
) -> list[FieldMappingResult]:
    results: list[FieldMappingResult] = []
    used: set[str] = set()
    exclusive = {"email", "phone", "first_name", "last_name", "resume_path"}
    for el in elements:
        if el.tag == "button":
            continue
        row = map_field(el, profile)
        pk = row.matched_profile_key
        if pk in used and pk in exclusive:
            row = FieldMappingResult(
                element_index=el.index,
                matched_profile_key=pk,
                value_to_fill=None,
                match_method=row.match_method,
                confidence=min(row.confidence, 0.4),
            )
        elif pk and row.value_to_fill:
            used.add(pk)
        results.append(row)
    return results
