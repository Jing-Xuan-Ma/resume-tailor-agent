"""Apply URL resolver: find + verify company ATS deep links.

Priority (caller responsibility):
  1) Existing deep link (Jobright Apply / JobSpy direct / JD body)
  2) This resolver (structured ATS APIs)
  3) Board fallback (Indeed/LinkedIn) — honest human entry
"""

from __future__ import annotations

from app.modules.job_discovery.apply_resolver.models import (
    ApplyCandidate,
    ResolveStatus,
    ResolveResult,
)
from app.modules.job_discovery.apply_resolver.service import resolve_apply_url

__all__ = [
    "ApplyCandidate",
    "ResolveStatus",
    "ResolveResult",
    "resolve_apply_url",
]
