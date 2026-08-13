"""CLI: scrape intern-list / Jobright mini-sites into SQLite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from app.modules.intern_list_scraper.categories import (
    CATEGORY_LABELS,
    TARGET_LINKS,
    TARGET_SLUGS,
    category_key,
    resolve_slugs,
)
from app.modules.intern_list_scraper.client import JobrightClient
from app.modules.intern_list_scraper.config import DEFAULT_CONFIG_PATH, ScrapeConfig, load_config
from app.modules.intern_list_scraper.db import (
    connect,
    get_watermark,
    known_job_ids,
    list_all_job_ids_for_slugs,
    list_job_ids_missing_details,
    max_posted_at,
    save_scrape_state,
    stats,
    upsert_detail,
    upsert_list_job,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Scrape intern-list.com via Jobright APIs into data/app.db."
        )
    )
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p.add_argument("--db", type=Path, default=None)
    p.add_argument(
        "--categories",
        nargs="*",
        default=None,
        help="Category slugs/aliases (default: target six: swe da aiml pm af ba)",
    )
    p.add_argument(
        "--targets",
        action="store_true",
        help="Force the default six target categories",
    )
    p.add_argument("--all", action="store_true", help="All intern:us categories")
    p.add_argument("--country", default=None, choices=["us", "ca"])
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max jobs per category (default from config, usually 1000)",
    )
    p.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max list pages per category (page_size from config, default 20)",
    )
    p.add_argument("--page-size", type=int, default=None)
    p.add_argument("--with-details", action="store_true", default=None)
    p.add_argument("--no-details", action="store_true")
    p.add_argument(
        "--backfill-details",
        action="store_true",
        help="Fetch JD details for existing list rows (all, or missing sections)",
    )
    p.add_argument(
        "--refresh-details",
        action="store_true",
        help="With --backfill-details, re-fetch even if detail already exists",
    )
    p.add_argument(
        "--details-limit",
        type=int,
        default=None,
        help="Max detail pages per category / backfill batch",
    )
    p.add_argument("--incremental", action="store_true", default=None)
    p.add_argument(
        "--full",
        action="store_true",
        help="Disable incremental; crawl up to limit/pages even if seen",
    )
    p.add_argument("--sleep", type=float, default=None)
    p.add_argument("--no-mirror", action="store_true")
    p.add_argument("--list-categories", action="store_true")
    p.add_argument("--show-config", action="store_true")
    return p


def _posted_at(item: dict[str, Any]) -> int | None:
    raw = item.get("postedAt")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def run_scrape(
    *,
    cfg: ScrapeConfig,
    slugs: list[str],
    db_path: Path | None,
    limit: int,
    max_pages: int | None,
    page_size: int,
    with_details: bool,
    details_limit: int | None,
    incremental: bool,
    mirror: bool,
    sleep: float,
    country: str,
) -> dict[str, Any]:
    client = JobrightClient(sleep_s=sleep)
    conn = connect(db_path)
    summary: dict[str, Any] = {"categories": [], "db": stats(conn)["db_path"]}
    try:
        for slug in slugs:
            cat = category_key(slug, country=country)
            label = CATEGORY_LABELS.get(slug, slug)
            watermark = get_watermark(conn, cat) if incremental else None
            if watermark is None and incremental:
                watermark = max_posted_at(conn, cat)
            known = known_job_ids(conn, cat) if incremental else set()
            print(f"\n== {label} ({cat}) ==")
            print(
                f"link: {TARGET_LINKS.get(slug, '')} | "
                f"incremental={incremental} watermark={watermark} known={len(known)}"
            )
            jobs, total, meta = client.iter_list(
                cat,
                limit=limit,
                page_size=page_size,
                max_pages=max_pages,
                since_posted_at=watermark if incremental else None,
                stop_on_known_ids=known if incremental else None,
            )
            created = updated = 0
            new_items: list[dict[str, Any]] = []
            newest_posted: int | None = watermark
            for item in jobs:
                job_id, is_new = upsert_list_job(
                    conn,
                    item,
                    category=cat,
                    slug=slug,
                    country=country,
                    also_job_listings=mirror,
                )
                posted = _posted_at(item)
                if posted is not None and (newest_posted is None or posted > newest_posted):
                    newest_posted = posted
                if is_new:
                    created += 1
                    new_items.append(item)
                else:
                    updated += 1
            conn.commit()
            save_scrape_state(
                conn,
                category=cat,
                slug=slug,
                last_posted_at=newest_posted,
                fetched=len(jobs),
                new_count=created,
            )
            conn.commit()
            print(
                f"list: fetched {len(jobs)}/{total} pages={meta['pages']} "
                f"stop={meta['stopped_reason']} | created={created} updated={updated}"
            )

            d_created = d_updated = d_fail = 0
            if with_details:
                detail_jobs = new_items if (incremental and cfg.details_only_for_new) else jobs
                if details_limit is not None:
                    detail_jobs = detail_jobs[:details_limit]
                for item in detail_jobs:
                    job_id = str(item.get("jobId") or "")
                    if not job_id:
                        continue
                    try:
                        detail = client.fetch_detail(job_id)
                        _, is_new = upsert_detail(
                            conn, detail, also_job_listings=mirror
                        )
                        if is_new:
                            d_created += 1
                        else:
                            d_updated += 1
                        if (d_created + d_updated) % 10 == 0:
                            conn.commit()
                    except Exception as e:  # noqa: BLE001
                        d_fail += 1
                        print(f"  detail fail {job_id}: {e}", file=sys.stderr)
                conn.commit()
                print(
                    f"detail: created={d_created} updated={d_updated} failed={d_fail}"
                )

            summary["categories"].append(
                {
                    "slug": slug,
                    "category": cat,
                    "fetched": len(jobs),
                    "total": total,
                    "created": created,
                    "updated": updated,
                    "detail_created": d_created,
                    "detail_updated": d_updated,
                    "detail_failed": d_fail,
                    "meta": meta,
                }
            )
    finally:
        summary["stats"] = stats(conn)
        conn.close()
    return summary


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config)

    if args.list_categories:
        print("Target six:")
        for slug in TARGET_SLUGS:
            print(f"  {slug:28} {CATEGORY_LABELS.get(slug, '')}  {TARGET_LINKS.get(slug, '')}")
        print("\nAll known:")
        for slug, label in CATEGORY_LABELS.items():
            print(f"  {slug:28} {label}")
        return 0

    if args.show_config:
        print(f"config: {args.config}")
        print(cfg)
        return 0

    try:
        use_targets = args.targets or (args.categories is None and not args.all)
        slugs = resolve_slugs(
            args.categories if not use_targets else None,
            country=args.country or cfg.country,
            all_categories=args.all,
            targets=use_targets,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    country = args.country or cfg.country
    sleep = args.sleep if args.sleep is not None else cfg.sleep_seconds
    db_path = args.db or (Path(cfg.db_path) if cfg.db_path else None)
    mirror = not args.no_mirror

    if args.backfill_details:
        conn = connect(db_path)
        client = JobrightClient(sleep_s=sleep)
        if args.refresh_details:
            job_ids = list_all_job_ids_for_slugs(conn, slugs=slugs)
        else:
            job_ids = list_job_ids_missing_details(conn, slugs=slugs)
        if args.details_limit is not None:
            job_ids = job_ids[: args.details_limit]
        print(f"backfill details: {len(job_ids)} jobs for {', '.join(slugs)}")
        created = updated = failed = 0
        try:
            for i, job_id in enumerate(job_ids, 1):
                try:
                    detail = client.fetch_detail(job_id)
                    _, is_new = upsert_detail(conn, detail, also_job_listings=mirror)
                    if is_new:
                        created += 1
                    else:
                        updated += 1
                    if i % 10 == 0:
                        conn.commit()
                        print(f"  … {i}/{len(job_ids)}")
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    print(f"  fail {job_id}: {e}", file=sys.stderr)
            conn.commit()
        finally:
            s = stats(conn)
            conn.close()
        print(f"done created={created} updated={updated} failed={failed}")
        print(f"list_total={s['list_total']} detail_total={s['detail_total']}")
        return 0 if failed == 0 else 1

    limit = args.limit if args.limit is not None else cfg.max_jobs_per_category
    page_size = args.page_size if args.page_size is not None else cfg.page_size
    max_pages = args.max_pages
    if max_pages is None and args.limit is None:
        max_pages = max(1, (limit + page_size - 1) // page_size)
    if args.no_details:
        with_details = False
    elif args.with_details:
        with_details = True
    else:
        with_details = cfg.with_details
    if args.full:
        incremental = False
    elif args.incremental:
        incremental = True
    else:
        incremental = cfg.incremental
    details_limit = args.details_limit

    print(f"db: {db_path or '(default app.db)'}")
    print(f"categories: {', '.join(slugs)}")
    print(
        f"limit={limit} max_pages={max_pages} page_size={page_size} "
        f"incremental={incremental} with_details={with_details}"
    )

    summary = run_scrape(
        cfg=cfg,
        slugs=slugs,
        db_path=db_path,
        limit=limit,
        max_pages=max_pages,
        page_size=page_size,
        with_details=with_details,
        details_limit=details_limit,
        incremental=incremental,
        mirror=mirror,
        sleep=sleep,
        country=country,
    )
    s = summary["stats"]
    print("\n== DB stats ==")
    print(f"list_total={s['list_total']} detail_total={s['detail_total']}")
    for slug, n in list(s["by_slug"].items())[:20]:
        print(f"  {slug}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
