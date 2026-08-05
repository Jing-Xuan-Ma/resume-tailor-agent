"""Standard JSON contract between Decision Engine and Drivers."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ATSType(str, Enum):
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    ICIMS = "icims"
    UNKNOWN = "unknown"


class InteractiveElement(BaseModel):
    index: int
    tag: str  # input | select | textarea | button
    element_type: Optional[str] = None  # text|email|tel|file|checkbox|radio|...
    label: str = ""
    current_value: Optional[str] = None
    options: Optional[list[str]] = None
    required: bool = False
    visible: bool = True
    # Driver-private hints (Playwright / extension). Engine may read frame_index for summaries.
    selector: Optional[str] = None
    frame_index: int = 0
    frame_url: Optional[str] = None
    in_iframe: bool = False


class DOMSnapshot(BaseModel):
    url: str
    page_title: str = ""
    elements: list[InteractiveElement] = Field(default_factory=list)
    screenshot_base64: Optional[str] = None
    form_stage: Optional[str] = None
    frame_count: int = 1


class ATSDetectionResult(BaseModel):
    ats_type: ATSType
    confidence: float = 0.0
    detection_method: str = "fallback"  # domain_pattern | dom_signature | fallback


class FieldMappingResult(BaseModel):
    element_index: int
    matched_profile_key: Optional[str] = None
    value_to_fill: Optional[str] = None
    match_method: Literal["rule", "semantic", "llm", "unmatched"] = "unmatched"
    confidence: float = 0.0


class ScreenerAnswer(BaseModel):
    element_index: int
    question_text: str
    generated_answer: str
    evidence_check_passed: bool
    evidence_sources: list[str] = Field(default_factory=list)
    needs_human_review: bool = True


class ActionInstruction(BaseModel):
    action: Literal[
        "fill",
        "click",
        "select",
        "upload_file",
        "wait",
        "pause_for_human",
        "submit",
    ]
    element_index: Optional[int] = None
    value: Optional[str] = None
    file_path: Optional[str] = None
    reason: str = ""
    requires_confirmation: bool = False


class EngineResponse(BaseModel):
    instructions: list[ActionInstruction] = Field(default_factory=list)
    stage: Literal["filling", "awaiting_human_review", "ready_to_submit", "error"] = "filling"
    summary_for_human: str = ""
    ats: Optional[ATSDetectionResult] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class EngineStepRequest(BaseModel):
    dom_snapshot: DOMSnapshot
    job_info: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    resume_facts: dict[str, Any] = Field(default_factory=dict)
    conversation: list[dict[str, Any]] = Field(default_factory=list)
    # When True, Engine may emit action=submit (still requires_confirmation by default).
    # Data-safety default: False → pause_for_human at ready_to_submit.
    allow_submit: bool = False
    mock: bool = False
