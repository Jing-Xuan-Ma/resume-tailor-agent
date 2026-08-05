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
    from entrypoints.standalone_app.playwright_driver import build_selector_for

    el = InteractiveElement(index=0, tag="input", label="Email", selector="#email")
    assert build_selector_for(el) == "#email"


@pytest.mark.asyncio
async def test_execute_skips_pause_and_submit():
    from entrypoints.standalone_app import playwright_driver as pd

    class DummyLocator:
        def __init__(self, page):
            self.page = page

        @property
        def first(self):
            return self

        async def fill(self, val, timeout=0):
            self.page.fills.append(val)

        async def dispatch_event(self, *_a, **_k):
            return None

        async def click(self, timeout=0):
            return None

        async def count(self):
            return 1

    class DummyPage:
        def __init__(self):
            self.fills = []
            self.frames = []
            self.main_frame = self

        def locator(self, sel):
            self.last_sel = sel
            return DummyLocator(self)

        async def wait_for_timeout(self, ms):
            return None

        async def wait_for_load_state(self, *_a, **_k):
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
    assert page.fills == ["a@b.com"]
    assert page.last_sel == "#email"
