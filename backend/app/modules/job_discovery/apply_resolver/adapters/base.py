"""Base ATS search adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.modules.job_discovery.apply_resolver.models import ApplyCandidate


class AtsSearchAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def detect_hints(self, hints: dict[str, Any]) -> dict[str, Any] | None:
        """Return platform-specific connection info if hints identify this ATS."""

    @abstractmethod
    def search(
        self,
        *,
        title: str,
        location: str | None = None,
        connection: dict[str, Any],
        limit: int = 20,
    ) -> list[ApplyCandidate]:
        ...

    def career_search_url(self, connection: dict[str, Any], title: str) -> str | None:
        return None
