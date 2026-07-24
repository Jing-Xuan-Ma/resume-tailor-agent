"""
Domain events for inter-module communication via EventBus.
Modules should not call each other directly; they publish and subscribe to events.
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal, Optional, Any
from uuid import UUID


def utcnow() -> datetime:
    return datetime.now(UTC)


# =============================================================================
# Resume Tailor Events
# =============================================================================

@dataclass
class ResumeTailoredEvent:
    """Emitted when a resume tailoring session completes."""
    user_id: UUID
    resume_id: UUID
    tailored_resume_id: UUID
    job_id: Optional[UUID] = None
    tailoring_summary: dict = field(default_factory=dict)
    ats_score_estimate: Optional[float] = None
    timestamp: datetime = field(default_factory=utcnow)


@dataclass
class UserFeedbackEvent:
    """Emitted when user provides feedback on a tailored resume."""
    user_id: UUID
    tailored_resume_id: UUID
    feedback_type: Literal["accepted", "rejected", "modified"]
    original_text: Optional[str] = None
    modified_text: Optional[str] = None
    comment: Optional[str] = None
    timestamp: datetime = field(default_factory=utcnow)


# =============================================================================
# Chat Events
# =============================================================================

@dataclass
class ConversationTurnEvent:
    """Emitted on every conversation turn."""
    session_id: UUID
    user_id: UUID
    role: Literal["user", "assistant"]
    content: str
    agent_state: Optional[str] = None
    timestamp: datetime = field(default_factory=utcnow)


# =============================================================================
# Job Discovery Events
# =============================================================================

@dataclass
class JobDiscoveredEvent:
    user_id: UUID
    job_id: UUID
    source_platform: str
    match_score: float


@dataclass
class JobScoredEvent:
    user_id: UUID
    job_id: UUID
    match_score: float
    passed_threshold: bool  # e.g., > 85%


# =============================================================================
# Event Bus
# =============================================================================

from collections import defaultdict
from typing import Callable, Awaitable


class EventBus:
    """Simple async event bus for decoupled module communication."""

    def __init__(self):
        self._handlers: dict[type, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: Callable[[Any], Awaitable[None]]):
        self._handlers[event_type].append(handler)

    async def publish(self, event):
        event_type = type(event)
        try:
            from app import db

            payload = asdict(event) if hasattr(event, "__dataclass_fields__") else {"value": str(event)}
            db.save_event(event_type.__name__, payload)
        except Exception:
            pass
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            await handler(event)


# Global event bus instance (to be imported by modules)
event_bus = EventBus()
