"""Phase 1: shopping-cart apply queue status machine."""

from __future__ import annotations

from app.modules.shopping_cart import store
from app.modules.shopping_cart.apply_pipeline import (
    jobright_url_for,
    start_apply_batch,
    summarize_apply,
)


def test_jobright_url_template() -> None:
    url = jobright_url_for("6a52cafd8a74e077472f6211")
    assert "6a52cafd8a74e077472f6211" in url
    assert url.startswith("https://jobright.ai/")


def test_start_apply_queues_eligible_items(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    store.save_cart_meta(
        cart_id,
        {
            "cart_id": cart_id,
            "user_id": "user-1",
            "status": "ready",
            "items": [
                {
                    "item_id": item_id,
                    "intern_job_id": "abc123",
                    "company": "Acme",
                    "position": "Intern",
                    "ok": True,
                    "status": "ready_md",
                },
                {
                    "item_id": store.new_cart_id(),
                    "intern_job_id": "bad",
                    "ok": False,
                    "status": "failed",
                    "error": "boom",
                },
            ],
        },
    )

    result = start_apply_batch(cart_id=cart_id, user_id="user-1")
    assert result["queued_count"] == 1
    assert result["queued"][0]["item_id"] == item_id
    assert result["queued"][0]["apply"]["status"] == "queued"
    assert "abc123" in (result["queued"][0]["apply"].get("jobright_url") or "")
    assert len(result["skipped"]) == 1

    meta = store.load_cart_meta(cart_id)
    assert meta is not None
    summary = summarize_apply(meta)
    assert summary["queued"] == 1

    # Second start should skip already-queued item
    again = start_apply_batch(cart_id=cart_id, user_id="user-1")
    assert again["queued_count"] == 0


def test_start_apply_rejects_wrong_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    store.save_cart_meta(
        cart_id,
        {
            "cart_id": cart_id,
            "user_id": "owner",
            "items": [],
        },
    )
    try:
        start_apply_batch(cart_id=cart_id, user_id="other")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "mismatch" in str(exc).lower()
