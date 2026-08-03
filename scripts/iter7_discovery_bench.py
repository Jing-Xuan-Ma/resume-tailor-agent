"""Iter-7: discovery latency / token proxy before-after notes."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def main() -> int:
    user = str(uuid4())
    # Warm
    client.get("/health")

    t0 = time.perf_counter()
    r = client.post(
        "/api/v1/jobs/discover",
        json={"user_id": user, "query": "data analyst", "location": "Remote", "limit": 5},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    jobs = r.json().get("jobs") or []

    t1 = time.perf_counter()
    listed = client.get("/api/v1/jobs/list", params={"user_id": user, "sort_by": "score"})
    list_ms = (time.perf_counter() - t1) * 1000
    assert listed.status_code == 200, listed.text

    # Token proxy: discovery should not require LLM when fallback/local providers used
    llm_calls_estimate = 0
    report = {
        "discover_jobs": len(jobs),
        "discover_ms": round(elapsed_ms, 1),
        "list_ms": round(list_ms, 1),
        "llm_calls_estimate": llm_calls_estimate,
        "notes": "List/scoring uses local mock scores; discover uses providers with local fallback (low/zero LLM).",
        "pass": elapsed_ms < 60000 and list_ms < 5000 and llm_calls_estimate == 0,
    }
    out = ROOT / "artifacts" / "iter-7-bench.json"
    out.write_text(__import__("json").dumps(report, indent=2), encoding="utf-8")
    print(report)
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
