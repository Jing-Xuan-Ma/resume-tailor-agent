"""Playwright driver helpers — selector / instruction gating (no browser)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.form_fill_engine.schemas import ActionInstruction, InteractiveElement


def test_build_selector_prefers_capture_selector():
    # Import from entrypoints package on repo root
    from entrypoints.standalone_app.playwright_driver import build_selector_for

    el = InteractiveElement(
        index=0,
        tag="input",
        label="Email",
        selector="#email",
    )
    assert build_selector_for(el) == "#email"


@pytest.mark.asyncio
async def test_execute_skips_pause_and_submit(monkeypatch):
    from entrypoints.standalone_app import playwright_driver as pd

    class DummyPage:
        def __init__(self):
            self.fills = []

        async def fill(self, sel, val):
            self.fills.append((sel, val))

        async def wait_for_timeout(self, ms):
            return None

    page = DummyPage()
    els = [InteractiveElement(index=0, tag="input", label="Email", selector="#email")]

    await pd.execute_instruction(
        page,
        ActionInstruction(action="pause_for_human", reason="stop", requires_confirmation=True),
        els,
    )
    await pd.execute_instruction(
        page,
        ActionInstruction(action="submit", reason="nope", requires_confirmation=True),
        els,
    )
    await pd.execute_instruction(
        page,
        ActionInstruction(action="fill", element_index=0, value="a@b.com", requires_confirmation=True),
        els,
    )
    assert page.fills == []

    await pd.execute_instruction(
        page,
        ActionInstruction(action="fill", element_index=0, value="a@b.com"),
        els,
    )
    assert page.fills == [("#email", "a@b.com")]
