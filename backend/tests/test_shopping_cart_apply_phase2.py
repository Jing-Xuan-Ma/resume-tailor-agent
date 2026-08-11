"""Phase 2: shopping-cart Jobright → ATS navigation worker."""

from __future__ import annotations

from app.modules.shopping_cart import service, store
from app.modules.shopping_cart.apply_pipeline import start_apply_batch, summarize_apply
from app.modules.shopping_cart.apply_worker import process_cart_queue, process_queued_item
from app.modules.shopping_cart.jobright_nav import detect_ats_type, resolve_ats_url_for_item


def _seed_cart(tmp_path, monkeypatch, *, source_url: str | None = None):
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
                    "intern_job_id": "6a52cafd8a74e077472f6211",
                    "company": "ASM Global",
                    "position": "Intern",
                    "ok": True,
                    "status": "ready_md",
                    "source_url": source_url,
                }
            ],
        },
    )
    return cart_id, item_id


def test_detect_ats_type_workday() -> None:
    assert (
        detect_ats_type("https://asmglobal.wd1.myworkdayjobs.com/en-US/ASM_Global/job/x")
        == "workday"
    )


def test_resolve_prefers_scraped_when_live_off(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.shopping_cart.jobright_nav.settings.CART_APPLY_LIVE_NAV",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.jobright_nav.settings.CART_APPLY_LIVE_NAV_FALLBACK",
        False,
        raising=False,
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.jobright_nav.resolve_ats_from_scraped",
        lambda **kwargs: {
            "ok": True,
            "ats_url": "https://asmglobal.wd1.myworkdayjobs.com/en-US/ASM_Global/job/x",
            "ats_type": "workday",
            "method": "scraped_apply_url",
        },
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.jobright_nav.navigate_jobright_to_ats",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("live nav should not run")),
    )
    out = resolve_ats_url_for_item(
        intern_job_id="6a52cafd8a74e077472f6211",
        jobright_url="https://jobright.ai/jobs/info/6a52cafd8a74e077472f6211",
        source_url="https://asmglobal.wd1.myworkdayjobs.com/en-US/ASM_Global/job/x",
    )
    assert out["ok"] is True
    assert out["ats_type"] == "workday"
    assert "myworkdayjobs.com" in out["ats_url"]


def test_process_queued_item_reaches_on_ats(tmp_path, monkeypatch) -> None:
    cart_id, item_id = _seed_cart(
        tmp_path,
        monkeypatch,
        source_url="https://asmglobal.wd1.myworkdayjobs.com/en-US/ASM_Global/job/x",
    )
    start_apply_batch(cart_id=cart_id, user_id="user-1")

    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.resolve_ats_url_for_item",
        lambda **kwargs: {
            "ok": True,
            "ats_url": "https://asmglobal.wd1.myworkdayjobs.com/en-US/ASM_Global/job/x",
            "ats_type": "workday",
            "method": "scraped_apply_url",
        },
    )

    result = process_queued_item(cart_id=cart_id, item_id=item_id)
    assert result["ok"] is True
    assert result["apply"]["status"] == "on_ats"
    assert result["apply"]["ats_type"] == "workday"
    assert "myworkdayjobs.com" in (result["apply"].get("ats_url") or "")

    meta = store.load_cart_meta(cart_id)
    assert summarize_apply(meta)["on_ats"] == 1


def test_process_queued_item_marks_failed(tmp_path, monkeypatch) -> None:
    cart_id, item_id = _seed_cart(tmp_path, monkeypatch)
    start_apply_batch(cart_id=cart_id, user_id="user-1")
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.resolve_ats_url_for_item",
        lambda **kwargs: {"ok": False, "error": "original_job_post_not_found", "method": "none"},
    )
    result = process_queued_item(cart_id=cart_id, item_id=item_id)
    assert result["ok"] is False
    assert result["apply"]["status"] == "failed"
    assert "original_job_post" in (result["apply"].get("error") or "")


def test_start_apply_processes_phase2(tmp_path, monkeypatch) -> None:
    cart_id, _item_id = _seed_cart(
        tmp_path,
        monkeypatch,
        source_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.resolve_ats_url_for_item",
        lambda **kwargs: {
            "ok": True,
            "ats_url": "https://boards.greenhouse.io/acme/jobs/1",
            "ats_type": "greenhouse",
            "method": "scraped_apply_url",
        },
    )
    # Keep this test Phase-2-scoped (Phase 3 covered separately).
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.process_on_ats_item",
        lambda **kwargs: {
            "item_id": kwargs.get("item_id"),
            "skipped": True,
            "reason": "phase2_only_test",
        },
    )
    out = service.start_apply(cart_id=cart_id, user_id="user-1", process_now=True)
    assert out["queued_count"] == 1
    assert out["ok_count"] == 1
    assert out["apply_summary"]["on_ats"] == 1


def test_process_cart_queue_batch(tmp_path, monkeypatch) -> None:
    cart_id, item_id = _seed_cart(tmp_path, monkeypatch)
    start_apply_batch(cart_id=cart_id, user_id="user-1")
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.resolve_ats_url_for_item",
        lambda **kwargs: {
            "ok": True,
            "ats_url": "https://jobs.lever.co/acme/abc",
            "ats_type": "lever",
            "method": "scraped_apply_url",
        },
    )
    out = process_cart_queue(cart_id=cart_id, user_id="user-1", through_phase=2)
    assert out["processed_count"] == 1
    assert out["ok_count"] == 1
    meta = store.load_cart_meta(cart_id)
    item = next(i for i in meta["items"] if i["item_id"] == item_id)
    assert item["apply"]["status"] == "on_ats"
