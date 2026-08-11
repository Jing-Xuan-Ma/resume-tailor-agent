"""Phase 3: Apply → Autofill with Resume on ATS entry."""

from __future__ import annotations

from pathlib import Path

from app.modules.application_engine.ats_apply_entry import (
    apply_and_autofill_resume,
    workday_entry_fixture_uri,
)
from app.modules.application_engine.browser_session import BrowserSession
from app.modules.shopping_cart import service, store
from app.modules.shopping_cart.apply_worker import process_on_ats_item, resolve_confirmed_resume_pdf


def _seed_on_ats(tmp_path, monkeypatch, *, with_pdf: bool = True, ats_url: str | None = None):
    import json

    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    company, position = "ASM Global", "Intern"
    d = store.item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
    resume_path = None
    if with_pdf:
        resume_path = d / "resume.pdf"
        resume_path.write_bytes(b"%PDF-1.4 sandbox resume")
        (d / "meta.json").write_text(
            json.dumps({"status": "confirmed", "resume_pdf_path": str(resume_path)}),
            encoding="utf-8",
        )

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
                    "company": company,
                    "position": position,
                    "ok": True,
                    "status": "confirmed" if with_pdf else "ready_md",
                    "apply": {
                        "status": "on_ats",
                        "ats_url": ats_url or workday_entry_fixture_uri(),
                        "ats_type": "workday",
                        "jobright_url": "https://jobright.ai/jobs/info/6a52cafd8a74e077472f6211",
                    },
                }
            ],
        },
    )
    return cart_id, item_id, str(resume_path) if resume_path else None


def test_resolve_confirmed_resume_pdf(tmp_path, monkeypatch) -> None:
    cart_id, item_id, resume_path = _seed_on_ats(tmp_path, monkeypatch, with_pdf=True)
    meta = store.load_cart_meta(cart_id)
    item = meta["items"][0]
    found = resolve_confirmed_resume_pdf(cart_id=cart_id, item=item)
    assert found == resume_path


def test_phase3_fails_without_resume_pdf(tmp_path, monkeypatch) -> None:
    cart_id, item_id, _ = _seed_on_ats(tmp_path, monkeypatch, with_pdf=False)
    out = process_on_ats_item(cart_id=cart_id, item_id=item_id)
    assert out["ok"] is False
    assert out["apply"]["status"] == "failed"
    assert out["apply"]["error"] == "confirm_resume_pdf_required"


def test_fixture_apply_autofill_attaches_resume() -> None:
    uri = workday_entry_fixture_uri()
    assert Path(uri.replace("file://", "")).exists() or uri.startswith("file:")
    # Write a tiny pdf next to fixture run
    resume = Path("/tmp/phase3_sandbox_resume.pdf")
    resume.write_bytes(b"%PDF-1.4 test")
    result = apply_and_autofill_resume(ats_url=uri, resume_path=str(resume), headless=True)
    assert result.get("submitted") is False
    assert result.get("ok") is True
    assert result.get("apply_clicked") is True
    assert result.get("autofill_clicked") is True
    assert result.get("resume_attached") is True
    assert result.get("next_screen") in {"create_account", "resume_attached"}


def test_browser_session_exposes_apply_autofill() -> None:
    assert hasattr(BrowserSession(), "apply_and_autofill_resume")


def test_process_on_ats_item_success(tmp_path, monkeypatch) -> None:
    cart_id, item_id, resume_path = _seed_on_ats(tmp_path, monkeypatch, with_pdf=True)
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.apply_and_autofill_resume",
        lambda **kwargs: {
            "ok": True,
            "apply_clicked": True,
            "autofill_clicked": True,
            "resume_attached": True,
            "next_screen": "create_account",
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "workday",
            "method": "playwright_apply_autofill",
            "screenshot_path": None,
            "submitted": False,
        },
    )
    out = process_on_ats_item(cart_id=cart_id, item_id=item_id)
    assert out["ok"] is True
    assert out["phase"] == 3
    apply = out["apply"]
    assert apply["status"] == "applying"
    assert apply["autofill_clicked"] is True
    assert apply["phase3_done"] is True
    assert apply["resume_path"] == resume_path
    assert apply["next_screen"] == "create_account"


def test_start_apply_runs_through_phase3(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    company, position = "Acme", "Intern"
    d = store.item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
    (d / "resume.pdf").write_bytes(b"%PDF-1.4")
    store.save_cart_meta(
        cart_id,
        {
            "cart_id": cart_id,
            "user_id": "user-1",
            "items": [
                {
                    "item_id": item_id,
                    "intern_job_id": "abc",
                    "company": company,
                    "position": position,
                    "ok": True,
                    "status": "confirmed",
                    "source_url": "https://boards.greenhouse.io/acme/jobs/1",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.resolve_ats_url_for_item",
        lambda **kwargs: {
            "ok": True,
            "ats_url": workday_entry_fixture_uri(),
            "ats_type": "workday",
            "method": "scraped_apply_url",
        },
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.apply_and_autofill_resume",
        lambda **kwargs: {
            "ok": True,
            "apply_clicked": True,
            "autofill_clicked": True,
            "resume_attached": True,
            "next_screen": "create_account",
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "workday",
            "method": "playwright_apply_autofill",
            "submitted": False,
        },
    )
    # Keep this test Phase-3-scoped (Phase 4 covered separately).
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.process_applying_item",
        lambda **kwargs: {
            "item_id": kwargs.get("item_id"),
            "skipped": True,
            "reason": "phase3_only_test",
        },
    )
    out = service.start_apply(cart_id=cart_id, user_id="user-1", process_now=True)
    assert out["ok_count"] >= 1
    meta = store.load_cart_meta(cart_id)
    item = meta["items"][0]
    assert item["apply"]["status"] == "applying"
    assert item["apply"]["phase3_done"] is True
