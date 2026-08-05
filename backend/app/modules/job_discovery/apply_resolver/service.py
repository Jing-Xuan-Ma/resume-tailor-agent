"""Orchestrate ATS adapters → match → light verify → ResolveResult."""

from __future__ import annotations

from typing import Any

from app.modules.job_discovery.apply_resolver.adapters import adapters_for_hints
from app.modules.job_discovery.apply_resolver.cache import get_company_ats, put_company_ats
from app.modules.job_discovery.apply_resolver.match import pick_best
from app.modules.job_discovery.apply_resolver.models import ResolveResult, ResolveStatus
from app.modules.job_discovery.apply_resolver.verify import verify_apply_url


def resolve_apply_url(
    *,
    company: str | None,
    title: str | None,
    location: str | None = None,
    raw_text: str | None = None,
    hints: dict[str, Any] | None = None,
    verify: bool = True,
) -> ResolveResult:
    """Find a usable company ATS deep link for company+title.

    ``hints`` may include apply_url / source_url / career_url / raw_text fragments
    that identify the ATS tenant (e.g. thin Workday ``.../FRS``).
    """
    company_s = (company or "").strip()
    title_s = (title or "").strip()
    if not title_s:
        return ResolveResult(
            status=ResolveStatus.NOT_FOUND,
            message="missing job title — cannot search ATS",
        )

    hint_bag: dict[str, Any] = dict(hints or {})
    if raw_text and "raw_text" not in hint_bag:
        hint_bag["raw_text"] = raw_text

    cached = False
    if company_s:
        cached_row = get_company_ats(company_s)
        if cached_row:
            cached = True
            # cached tenant fills gaps; explicit hints still win via detect order
            for k, v in cached_row.items():
                hint_bag.setdefault(k, v)

    pairs = adapters_for_hints(hint_bag)
    if not pairs:
        return ResolveResult(
            status=ResolveStatus.NOT_FOUND,
            message=(
                "no ATS tenant detected from hints — need a career-site clue "
                "(Workday/Greenhouse/Lever URL) or company cache entry"
            ),
            cached_tenant=cached,
        )

    last_error = ""
    for adapter, conn in pairs:
        try:
            candidates = adapter.search(
                title=title_s,
                location=location,
                connection=conn,
                limit=20,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        best = pick_best(
            candidates,
            title=title_s,
            location=location,
            raw_text=raw_text or str(hint_bag.get("raw_text") or ""),
        )
        career = adapter.career_search_url(conn, title_s)
        if not best:
            last_error = f"{adapter.name}: no title match among {len(candidates)} hits"
            continue

        # Persist tenant mapping for next time
        if company_s:
            put_company_ats(
                company_s,
                platform=adapter.name,
                tenant=str(conn.get("tenant") or ""),
                site=str(conn.get("site") or ""),
                host=str(conn.get("host") or ""),
                career_url=str(conn.get("career_url") or ""),
                extra={"wd": conn.get("wd")} if conn.get("wd") else None,
            )

        if not verify:
            return ResolveResult(
                status=ResolveStatus.UNVERIFIED,
                url=best.url,
                candidate=best,
                message="resolved without verification",
                adapter=adapter.name,
                career_search_url=career,
                cached_tenant=cached,
            )

        vr = verify_apply_url(best.url, title=title_s)
        if vr.kind == "ok":
            return ResolveResult(
                status=ResolveStatus.VERIFIED,
                url=best.url,
                candidate=best,
                message=f"verified via {adapter.name} (confidence={best.confidence:.2f})",
                adapter=adapter.name,
                verify_detail=vr.detail,
                career_search_url=career,
                cached_tenant=cached,
            )
        if vr.kind == "uncertain":
            return ResolveResult(
                status=ResolveStatus.UNVERIFIED,
                url=best.url,
                candidate=best,
                message=(
                    f"found via {adapter.name} but could not verify "
                    f"(confidence={best.confidence:.2f}) — open and confirm yourself"
                ),
                adapter=adapter.name,
                verify_detail=vr.detail,
                career_search_url=career,
                cached_tenant=cached,
            )
        # explicit fail → try next adapter / treat as not found for this hit
        last_error = f"{adapter.name}: verify fail: {vr.detail}"
        # still expose career search as soft fallback
        return ResolveResult(
            status=ResolveStatus.NOT_FOUND,
            url=None,
            candidate=best,
            message=f"candidate failed verification: {vr.detail}",
            adapter=adapter.name,
            verify_detail=vr.detail,
            career_search_url=career,
            cached_tenant=cached,
        )

    return ResolveResult(
        status=ResolveStatus.NOT_FOUND,
        message=last_error or "ATS search returned no usable match",
        cached_tenant=cached,
        adapter=pairs[0][0].name if pairs else None,
        career_search_url=pairs[0][0].career_search_url(pairs[0][1], title_s) if pairs else None,
    )
