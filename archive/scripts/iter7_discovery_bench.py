"""Iter-7: discovery latency / token proxy before-after notes."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _discover(user: str, query: str = "data analyst") -> tuple[float, int]:
    t0 = time.perf_counter()
    r = client.post(
        "/api/v1/jobs/discover",
        json={"user_id": user, "query": query, "location": "Remote", "limit": 5},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert r.status_code == 200, r.text
    return elapsed_ms, len(r.json().get("jobs") or [])


def main() -> int:
    user = str(uuid4())
    client.get("/health")

    # Cold path (providers + local parse, no LLM)
    cold_ms, cold_n = _discover(user, "data analyst")
    # Warm path (orchestrator TTL cache hit for same query/user)
    warm_ms, warm_n = _discover(user, "data analyst")

    t1 = time.perf_counter()
    listed = client.get("/api/v1/jobs/list", params={"user_id": user, "sort_by": "score"})
    list_ms = (time.perf_counter() - t1) * 1000
    assert listed.status_code == 200, listed.text

    report = {
        "before": {
            "discover_ms": 10306.0,
            "list_ms": 2.7,
            "llm_calls_estimate": "N (LLM JD parse per job on discover)",
            "notes": "Baseline measured before Iter-7 cache + local parse",
        },
        "after": {
            "discover_cold_ms": round(cold_ms, 1),
            "discover_warm_ms": round(warm_ms, 1),
            "discover_jobs": cold_n,
            "list_ms": round(list_ms, 1),
            "llm_calls_estimate": 0,
            "notes": (
                "Dedupe in orchestrator; 300s TTL discover cache; "
                "discover path uses local tokenize parse (no LLM)."
            ),
        },
        "pass": (
            cold_n >= 1
            and warm_n >= 1
            and warm_ms < cold_ms * 0.5
            and list_ms < 5000
        ),
    }
    out = ROOT / "artifacts" / "iter-7-bench.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
