"""Phase 4: Create Account / Sign In → registered."""

from __future__ import annotations

import json
from pathlib import Path

from app.modules.application_engine.ats_account import (
    create_or_sign_in,
    load_ats_credentials,
    mask_email,
    sanitize_account_payload,
    validate_ats_password,
)
from app.modules.application_engine.ats_apply_entry import workday_entry_fixture_uri
from app.modules.application_engine.browser_session import BrowserSession
from app.modules.shopping_cart import service, store
from app.modules.shopping_cart.apply_worker import process_applying_item


def test_mask_email_and_sanitize() -> None:
    assert mask_email("alice@example.com") == "a***@example.com"
    cleaned = sanitize_account_payload(
        {
            "ok": True,
            "email": "alice@example.com",
            "password": "Secret1!",
            "note": "Secret1! leaked",
        }
    )
    assert "email" not in cleaned
    assert cleaned["email_masked"] == "a***@example.com"
    assert cleaned["password"] == "***"
    assert "Secret1!" not in cleaned["note"]


def test_validate_ats_password_rules() -> None:
    assert validate_ats_password("ChangeMe1!")["ok"] is True
    assert validate_ats_password("short1!")["ok"] is False
    assert validate_ats_password("nouppercase1!")["ok"] is False


def test_load_credentials_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL", "")
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD", ""
    )
    out = load_ats_credentials()
    assert out["ok"] is False
    assert out["error"] == "ats_credentials_not_configured"


def _seed_applying(tmp_path, monkeypatch, *, ats_url: str | None = None):
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
                        "status": "applying",
                        "ats_url": ats_url or workday_entry_fixture_uri(),
                        "ats_type": "workday",
                        "phase3_done": True,
                        "autofill_clicked": True,
                        "resume_path": str(resume_path),
                    },
                }
            ],
        },
    )
    return cart_id, item_id, str(resume_path)


def test_phase4_fails_without_credentials(tmp_path, monkeypatch) -> None:
    cart_id, item_id, _ = _seed_applying(tmp_path, monkeypatch)
    monkeypatch.setattr("app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL", "")
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD", ""
    )
    out = process_applying_item(cart_id=cart_id, item_id=item_id)
    assert out["ok"] is False
    assert out["apply"]["status"] == "failed"
    assert out["apply"]["error"] == "ats_credentials_not_configured"
    assert "password" not in json.dumps(out["apply"])


def test_fixture_create_account_registers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL",
        "fresh.user@example.com",
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD",
        "ChangeMe1!",
    )
    resume = Path("/tmp/phase4_sandbox_resume.pdf")
    resume.write_bytes(b"%PDF-1.4 test")
    result = create_or_sign_in(
        ats_url=workday_entry_fixture_uri(),
        resume_path=str(resume),
        headless=True,
        ensure_entry=True,
    )
    assert result.get("submitted") is False
    assert result.get("ok") is True
    assert result.get("auth_mode") in {"create_account", "already_in"}
    assert "password" not in result or result.get("password") in (None, "", "***")
    assert result.get("email_masked", "").endswith("@example.com")


def test_fixture_email_exists_falls_back_to_signin(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_EMAIL",
        "exists@example.com",
    )
    monkeypatch.setattr(
        "app.modules.application_engine.ats_account.settings.ATS_DEFAULT_PASSWORD",
        "ChangeMe1!",
    )
    resume = Path("/tmp/phase4_exists_resume.pdf")
    resume.write_bytes(b"%PDF-1.4 test")
    result = create_or_sign_in(
        ats_url=workday_entry_fixture_uri(),
        resume_path=str(resume),
        headless=True,
        ensure_entry=True,
    )
    assert result.get("ok") is True
    assert result.get("auth_mode") == "sign_in_after_email_exists"
    assert result.get("email_existed") is True


def test_process_applying_item_success(tmp_path, monkeypatch) -> None:
    cart_id, item_id, _ = _seed_applying(tmp_path, monkeypatch)
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
            "ok": True,
            "auth_mode": "create_account",
            "email_masked": "w***@example.com",
            "ats_url": kwargs.get("ats_url"),
            "ats_type": "workday",
            "method": "playwright_account",
            "submitted": False,
        },
    )
    out = process_applying_item(cart_id=cart_id, item_id=item_id)
    assert out["ok"] is True
    assert out["phase"] == 4
    assert out["apply"]["status"] == "registered"
    assert out["apply"]["phase4_done"] is True
    assert out["apply"]["email_masked"] == "w***@example.com"
    blob = json.dumps(out)
    assert "ChangeMe1!" not in blob


def test_browser_session_exposes_create_or_sign_in() -> None:
    assert hasattr(BrowserSession(), "create_or_sign_in")


def test_start_apply_through_phase4(tmp_path, monkeypatch) -> None:
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
        "app.modules.shopping_cart.apply_worker.process_registered_item",
        lambda **kwargs: {
            "item_id": kwargs.get("item_id"),
            "skipped": True,
            "reason": "phase4_only_test",
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
    assert out["phase"] == 5 or out.get("ok_count", 0) >= 1
    meta = store.load_cart_meta(cart_id)
    assert meta["items"][0]["apply"]["status"] == "registered"
    assert meta["items"][0]["apply"]["phase4_done"] is True
