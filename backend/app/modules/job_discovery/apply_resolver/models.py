"""Typed results for apply URL resolution + verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResolveStatus(str, Enum):
    """Three-way UI state — not a binary found/missing."""

    VERIFIED = "verified"  # ✅ light/heavy verify confirmed
    UNVERIFIED = "unverified"  # ⚠️ candidate found but verify timed out / blocked
    NOT_FOUND = "not_found"  # ❌ no usable deep link


@dataclass
class ApplyCandidate:
    title: str
    url: str
    req_id: str | None = None
    location: str | None = None
    posted_on: str | None = None
    confidence: float = 0.0
    adapter: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResolveResult:
    status: ResolveStatus
    url: str | None = None
    candidate: ApplyCandidate | None = None
    message: str = ""
    adapter: str | None = None
    verify_detail: str | None = None
    career_search_url: str | None = None  # soft fallback when job closed
    cached_tenant: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "url": self.url,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "message": self.message,
            "adapter": self.adapter,
            "verify_detail": self.verify_detail,
            "career_search_url": self.career_search_url,
            "cached_tenant": self.cached_tenant,
        }
