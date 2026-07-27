from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawJobLead:
    title: str
    company: str | None = None
    location: str | None = None
    source_url: str | None = None
    source_platform: str = "unknown"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        lines = [
            self.title,
            f"Company: {self.company or ''}",
            f"Location: {self.location or ''}",
            f"Source: {self.source_platform}",
            f"URL: {self.source_url or ''}",
            "",
            self.description or "",
        ]
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "raw_text": "\n".join(lines).strip(),
            "metadata": self.metadata,
        }


class BaseJobProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def discover(
        self,
        *,
        query: str,
        location: str | None = None,
        limit: int = 10,
    ) -> list[RawJobLead]:
        ...
