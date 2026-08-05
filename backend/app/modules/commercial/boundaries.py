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
        "auto_click_submit": False,
        "batch_one_click_all_submit": False,
        "cold_email_auto_send": bool(getattr(settings, "ENABLE_GMAIL_SEND", False)),
        "storage_backend": settings.STORAGE_BACKEND,
        "multi_tenant": bool(settings.ENABLE_MULTI_TENANT),
        "billing_enabled": bool(settings.ENABLE_BILLING),
        "job_sources": {
            "jobright_extension": True,
            "public_ats_apis": True,
            "jobspy": bool(settings.JOB_INDEX_ENABLE_JOBSPY),
            "adzuna": bool(settings.JOB_INDEX_ENABLE_ADZUNA),
        },
        "notes": [
            "Default: never click live Submit without per-job user confirm.",
            "Email: mailto / mark-sent first; Gmail/SMTP only when ENABLE_GMAIL_SEND.",
            "SQLite remains default local store; set STORAGE_BACKEND=postgres for cloud.",
            "Billing and multi-tenant are off until explicitly enabled.",
        ],
    }


@router.get("/boundaries")
async def get_boundaries():
    return product_boundaries()
