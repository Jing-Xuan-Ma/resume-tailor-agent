"""Phase 5: ATS form fill → ready_to_submit with reviewable snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.application_engine.ats_apply_entry import workday_entry_fixture_uri
from app.modules.application_engine.ats_form_fill import (
    fill_ats_form_pause,
    load_fill_snapshot,
    profile_checklist,
)
from app.modules.application_engine.browser_session import BrowserSession
from app.modules.shopping_cart import service, store
from app.modules.shopping_cart.apply_worker import get_fill_review, process_registered_item


def _seed_registered(tmp_path, monkeypatch, *, ats_url: str | None = None):
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    company, position = "ASM Global", "Intern"
    d = store.item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
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
            "items": [
                {
                    "item_id": item_id,
                    "intern_job_id": "6a52cafd8a74e077472f6211",
                    "company": company,
                    "position": position,
                    "ok": True,
                    "status": "confirmed",
                    "apply": {
                        "status": "registered",
                        "ats_url": ats_url or workday_entry_fixture_uri(),
                        "ats_type": "workday",
                        "phase3_done": True,
                        "phase4_done": True,
                        "auth_mode": "create_account",
                        "resume_path": str(resume_path),
                    },
                }
            ],
        },
    )
    return cart_id, item_id, str(resume_path)


def test_profile_checklist_includes_submit_not_clicked() -> None:
    rows = profile_checklist(
        {
            "full_name": "A B",
            "first_name": "A",
            "last_name": "B",
            "email": "a@b.com",
            "phone": "1",
            "linkedin": "",
            "location": "",
            "work_authorized": "Yes",
            "resume_path": "/tmp/x.pdf",
        }
    )
    submit = next(r for r in rows if r["field"] == "submit_button")
    assert submit["value"] == "NOT_CLICKED"


def test_dry_run_snapshot_when_live_blocked(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.application_engine.ats_form_fill.settings.CART_APPLY_LIVE_ENTRY", False
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_form_fill.settings.ALLOW_LIVE_BROWSER_FILL", False
    )
    snap = tmp_path / "snap.json"
    out = fill_ats_form_pause(
        user_id="user-1",
        ats_url="https://example-company.myworkdayjobs.com/en-US/job/x",
        resume_path=None,
        snapshot_path=str(snap),
    )
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert out["submitted"] is False
    assert out["paused_before_submit"] is True
    assert any(r.get("field") == "submit_button" for r in out["filled_fields"])
    loaded = load_fill_snapshot(str(snap))
    assert loaded is not None
    assert loaded["method"] == "dry_run_profile_snapshot"


def test_fixture_fill_reaches_ready_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.application_engine.ats_form_fill.settings.ENABLE_BROWSER_FILL_PAUSE", True
    )
    resume = Path("/tmp/phase5_sandbox_resume.pdf")
    resume.write_bytes(b"%PDF-1.4 test")
    shot = tmp_path / "p5.png"
    snap = tmp_path / "p5.json"
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL",
        "fill.user@example.com",
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD",
        "ChangeMe1!",
    )
    out = fill_ats_form_pause(
        user_id="user-1",
        ats_url=workday_entry_fixture_uri(),
        resume_path=str(resume),
        screenshot_path=str(shot),
        snapshot_path=str(snap),
        ensure_registered_form=True,
    )
    assert out.get("submitted") is False
    assert out.get("paused_before_submit") is True
    assert out.get("ok") is True
    assert not out.get("browser_fill", {}).get("submit_leaked")
    assert snap.is_file()
    assert out.get("form_url")
    assert out.get("storage_state_path")
    assert Path(out["storage_state_path"]).is_file()
    assert any(
        "submit" in str(r.get("field") or "").lower() for r in out.get("filled_fields") or []
    )


def test_process_registered_item_persists_review(tmp_path, monkeypatch) -> None:
    cart_id, item_id, resume_path = _seed_registered(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.fill_ats_form_pause",
        lambda **kwargs: {
            "ok": True,
            "method": "playwright_fill_pause",
            "filled_fields": [
                {"field": "email", "value": "a@b.com", "tier": "auto"},
                {"field": "submit_button", "value": "NOT_CLICKED", "tier": "empty"},
            ],
            "profile_checklist": [{"field": "email", "value": "a@b.com", "tier": "auto"}],
            "fill_plan": [],
            "ats_url": kwargs.get("ats_url"),
            "form_url": (kwargs.get("ats_url") or "") + "#ready",
            "storage_state_path": str(
                Path(kwargs.get("snapshot_path") or tmp_path / "x").with_name("state.json")
            ),
            "ats_type": "workday",
            "screenshot_path": kwargs.get("screenshot_path"),
            "fill_snapshot_path": kwargs.get("snapshot_path"),
            "resume_path": resume_path,
            "submitted": False,
            "paused_before_submit": True,
        },
    )
    out = process_registered_item(cart_id=cart_id, item_id=item_id, user_id="user-1")
    assert out["ok"] is True
    assert out["phase"] == 5
    apply = out["apply"]
    assert apply["status"] == "ready_to_submit"
    assert apply["phase5_done"] is True
    assert apply["paused_before_submit"] is True
    assert apply["submitted"] is False
    assert apply.get("filled_fields")
    assert apply.get("form_url", "").endswith("#ready")
    assert apply.get("storage_state_path")

    Path(apply["fill_snapshot_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(apply["fill_snapshot_path"]).write_text(
        json.dumps(
            {
                "filled_fields": apply["filled_fields"],
                "profile_checklist": apply.get("profile_checklist"),
                "paused_before_submit": True,
                "submitted": False,
            }
        ),
        encoding="utf-8",
    )
    review = get_fill_review(cart_id=cart_id, item_id=item_id, user_id="user-1")
    assert review["apply_status"] == "ready_to_submit"
    assert len(review["steps"]) == 4
    assert review["review"]["submitted"] is False


def test_open_item_filled_form_restores_session(tmp_path, monkeypatch) -> None:
    from app.modules.shopping_cart.apply_worker import open_item_filled_form

    cart_id, item_id, _ = _seed_registered(tmp_path, monkeypatch)
    shot_dir = store.cart_dir(cart_id) / "_apply_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    state = shot_dir / "storage.json"
    state.write_text('{"cookies":[],"origins":[]}', encoding="utf-8")
    form_url = "https://example.myworkdayjobs.com/en-US/job/x/apply/submit"
    meta = store.load_cart_meta(cart_id)
    meta["items"][0]["apply"] = {
        **meta["items"][0]["apply"],
        "status": "ready_to_submit",
        "phase5_done": True,
        "form_url": form_url,
        "storage_state_path": str(state),
        "ats_url": form_url,
    }
    store.save_cart_meta(cart_id, meta)

    called: dict = {}

    def _fake_open(**kwargs):
        called.update(kwargs)
        return {
            "ok": True,
            "opened": True,
            "form_url": kwargs["form_url"],
            "session_restored": True,
            "method": "headed_restore",
            "message": "opened",
        }

    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.open_filled_form_page",
        _fake_open,
    )
    out = open_item_filled_form(cart_id=cart_id, item_id=item_id, user_id="user-1")
    assert out["ok"] is True
    assert out["form_url"] == form_url
    assert out["session_restored"] is True or out.get("refilled") is True
    assert called["form_url"] == form_url
    assert called["headless"] is False
    assert called.get("user_id") == "user-1" or "user_id" in called


def test_browser_session_exposes_fill_form_pause() -> None:
    assert hasattr(BrowserSession(), "fill_form_pause")


def test_start_apply_through_phase5(tmp_path, monkeypatch) -> None:
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
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.create_or_sign_in",
        lambda **kwargs: {
            "ok": True,
            "auth_mode": "create_account",
            "email_masked": "t***@example.com",
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "workday",
            "method": "playwright_account",
            "submitted": False,
        },
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.fill_ats_form_pause",
        lambda **kwargs: {
            "ok": True,
            "method": "playwright_fill_pause",
            "filled_fields": [{"field": "email", "value": "x", "tier": "auto"}],
            "profile_checklist": [{"field": "email", "value": "x", "tier": "auto"}],
            "fill_plan": [],
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "workday",
            "screenshot_path": kwargs.get("screenshot_path"),
            "fill_snapshot_path": kwargs.get("snapshot_path"),
            "submitted": False,
            "paused_before_submit": True,
        },
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL",
        "test@example.com",
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD",
        "ChangeMe1!",
    )
    out = service.start_apply(cart_id=cart_id, user_id="user-1", process_now=True)
    assert out["phase"] == 5
    meta = store.load_cart_meta(cart_id)
    assert meta["items"][0]["apply"]["status"] == "ready_to_submit"
    assert meta["items"][0]["apply"]["phase5_done"] is True
