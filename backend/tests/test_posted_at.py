from app.modules.job_discovery.posted_at import display_age_iso, extract_posted_at


def test_extract_publication_date():
    assert extract_posted_at({"publication_date": "2026-08-03T01:00:00"}) is not None


def test_extract_epoch_ms():
    iso = extract_posted_at({"date": 1722643200000})
    assert iso is not None
    assert "2024" in iso or "2025" in iso or "2026" in iso


def test_display_prefers_posted_over_scraped():
    out = display_age_iso(
        scraped_at="2026-08-01T00:00:00+00:00",
        metadata={"date_posted": "2026-08-03T12:00:00"},
    )
    assert out.startswith("2026-08-03")
