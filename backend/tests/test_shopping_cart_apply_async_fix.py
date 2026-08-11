"""Regression: cart apply must not call Playwright Sync API on the asyncio loop."""

from __future__ import annotations

import inspect

from app.modules.shopping_cart import router, store
from app.modules.shopping_cart.apply_pipeline import start_apply_batch


def test_apply_start_route_offloads_to_thread() -> None:
    src = inspect.getsource(router.start_apply)
    assert "asyncio.to_thread" in src
    src2 = inspect.getsource(router.process_apply)
    assert "asyncio.to_thread" in src2


def test_failed_items_can_requeue_and_clear_phase_flags(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    store.save_cart_meta(
        cart_id,
        {
            "cart_id": cart_id,
            "user_id": "user-1",
            "items": [
                {
                    "item_id": item_id,
                    "intern_job_id": "abc",
                    "company": "Acme",
                    "position": "Intern",
                    "ok": True,
                    "status": "confirmed",
                    "apply": {
                        "status": "failed",
                        "error": "Playwright Sync API inside the asyncio loop",
                        "ats_url": "https://example.com/job",
                        "phase3_done": True,
                        "phase4_done": True,
                        "autofill_clicked": True,
                    },
                }
            ],
        },
    )
    out = start_apply_batch(cart_id=cart_id, user_id="user-1")
    assert out["queued_count"] == 1
    meta = store.load_cart_meta(cart_id)
    apply = meta["items"][0]["apply"]
    assert apply["status"] == "queued"
    assert apply.get("error") is None
    assert "phase3_done" not in apply
    assert "phase4_done" not in apply
    assert "autofill_clicked" not in apply
