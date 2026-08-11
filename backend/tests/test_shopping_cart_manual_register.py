"""Manual register handoff after CAPTCHA blocks Phase 4."""

from __future__ import annotations

import json

from app.modules.shopping_cart import store
from app.modules.shopping_cart.apply_worker import (
    confirm_item_manual_register,
    process_applying_item,
)


def _seed_applying(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CART_ROOT", tmp_path)
    cart_id = store.new_cart_id()
    item_id = store.new_cart_id()
    company, position = "ByteDance", "Intern"
    d = store.item_dir(cart_id, company, position)
    d.mkdir(parents=True, exist_ok=True)
    resume_path = d / "resume.pdf"
    resume_path.write_bytes(b"%PDF-1.4")
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
                    "intern_job_id": "job-1",
                    "company": company,
                    "position": position,
                    "ok": True,
                    "status": "confirmed",
                    "apply": {
                        "status": "applying",
                        "ats_url": "https://jobs.example.com/apply/1",
                        "ats_type": "generic",
                        "phase3_done": True,
                        "autofill_clicked": True,
                        "resume_path": str(resume_path),
                    },
                }
            ],
        },
    )
    return cart_id, item_id


def test_phase4_captcha_marks_needs_manual_register(tmp_path, monkeypatch) -> None:
    cart_id, item_id = _seed_applying(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL",
        "worker@example.com",
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD",
        "ChangeMe1!",
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.create_or_sign_in",
        lambda **kwargs: {
            "ok": False,
            "error": "captcha_required",
            "message": "CAPTCHA detected",
            "email_masked": "w***@example.com",
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "generic",
            "submitted": False,
        },
    )
    out = process_applying_item(cart_id=cart_id, item_id=item_id)
    assert out["ok"] is False
    assert out["needs_manual_register"] is True
    apply = out["apply"]
    assert apply["status"] == "failed"
    assert apply["error"] == "captcha_required"
    assert apply["needs_manual_register"] is True
    assert "验证码" in (apply.get("manual_register_reason") or "")


def test_confirm_manual_register_continues_phase5(tmp_path, monkeypatch) -> None:
    cart_id, item_id = _seed_applying(tmp_path, monkeypatch)
    meta = store.load_cart_meta(cart_id)
    assert meta
    storage = tmp_path / "storage.json"
    storage.write_text("{}", encoding="utf-8")
    meta["items"][0]["apply"].update(
        {
            "status": "failed",
            "error": "captcha_required",
            "needs_manual_register": True,
            "manual_register_opened": True,
            "phase3_done": True,
            "manual_register_reason": "验证码无法自动完成",
            "register_storage_state_path": str(storage),
        }
    )
    store.save_cart_meta(cart_id, meta)

    monkeypatch.setattr(
        "app.modules.application_engine.manual_register.snapshot_and_close_register_page",
        lambda **kwargs: {
            "ok": True,
            "registered": True,
            "ats_url": "https://jobs.example.com/apply/1",
            "storage_state_path": str(storage),
        },
    )
    monkeypatch.setattr(
        "app.modules.shopping_cart.apply_worker.process_registered_item",
        lambda **kwargs: {
            "item_id": item_id,
            "ok": True,
            "phase": 5,
            "apply": {
                "status": "ready_to_submit",
                "phase4_done": True,
                "phase5_done": True,
            },
        },
    )

    out = confirm_item_manual_register(
        cart_id=cart_id, item_id=item_id, user_id="user-1", continue_apply=True
    )
    assert out["ok"] is True
    assert out["phase5"]["ok"] is True
    meta2 = store.load_cart_meta(cart_id)
    apply = meta2["items"][0]["apply"]
    assert apply.get("auth_mode") == "manual_user"
    assert apply.get("phase4_done") is True
    assert apply.get("needs_manual_register") is not True
