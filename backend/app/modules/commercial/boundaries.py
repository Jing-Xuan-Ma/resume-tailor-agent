"""Commercial / cloud product boundaries (Phase 5).

Defaults stay personal-safe: pause before submit, no mass email, SQLite OK in
development. Cloud/Postgres/multi-tenant gates are explicit.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


def product_boundaries() -> dict:
    return {
        "phase": "P5_commercial_scaffolding",
        "pause_before_submit_default": True,
        "allow_live_browser_fill": bool(settings.ALLOW_LIVE_BROWSER_FILL),
        "cart_apply_live_nav": bool(getattr(settings, "CART_APPLY_LIVE_NAV", False)),
        "cart_apply_live_entry": bool(getattr(settings, "CART_APPLY_LIVE_ENTRY", False)),
        "auto_click_submit": False,
        "batch_one_click_all_submit": False,
        "cold_email_auto_send": bool(getattr(settings, "ENABLE_GMAIL_SEND", False)),
        "storage_backend": settings.STORAGE_BACKEND,
        "multi_tenant": bool(settings.ENABLE_MULTI_TENANT),
        "billing_enabled": bool(settings.ENABLE_BILLING),
        "ats_default_email_configured": bool((settings.ATS_DEFAULT_EMAIL or "").strip()),
        "job_sources": {
            "intern_list_scraper": True,
            "jobright_job_pages": True,
            "public_ats_apis": True,
            "jobspy": bool(settings.JOB_INDEX_ENABLE_JOBSPY),
            "adzuna": bool(settings.JOB_INDEX_ENABLE_ADZUNA),
        },
        "apply_paths": {
            "shopping_cart_batch": True,
            "single_job_apply_workspace": True,
            "docs": "docs/APPLY_PIPELINE.md",
        },
        "notes": [
            "Default: never click live Submit without per-job user one-click confirm.",
            "Batch apply: shopping cart status machine (queued → … → ready_to_submit).",
            "Single job: Tailor Confirm → /apply fill-pause.",
            "ATS credentials: ATS_DEFAULT_EMAIL / ATS_DEFAULT_PASSWORD env only.",
            "Email: mailto / mark-sent first; Gmail/SMTP only when ENABLE_GMAIL_SEND.",
            "SQLite remains default local store; set STORAGE_BACKEND=postgres for cloud.",
        ],
    }


@router.get("/boundaries")
async def get_boundaries():
    return product_boundaries()
