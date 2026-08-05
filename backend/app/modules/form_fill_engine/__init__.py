"""Form-Fill Decision Engine — environment-agnostic action planning.

Drivers (Playwright / Chrome extension) capture DOMSnapshot JSON and
POST to /engine/step; Engine returns ActionInstruction lists only.
"""

from app.modules.form_fill_engine.schemas import (
    ActionInstruction,
    ATSDetectionResult,
    ATSType,
    DOMSnapshot,
    EngineResponse,
    EngineStepRequest,
    InteractiveElement,
)

__all__ = [
    "ActionInstruction",
    "ATSDetectionResult",
    "ATSType",
    "DOMSnapshot",
    "EngineResponse",
    "EngineStepRequest",
    "InteractiveElement",
]
