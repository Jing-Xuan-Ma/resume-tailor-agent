"""JobSpy integration with subprocess isolation.

Why isolate:
  `python-jobspy` (pinned numpy) can hard-crash the interpreter on Windows
  Python 3.14 — ACCESS_VIOLATION kills the whole API process. Scraping in a
  child process keeps uvicorn alive even when JobSpy dies.

Why that can still drag the API:
  A sync `subprocess.run` inside an async route blocks the event loop for the
  full scrape (up to timeout). Callers must run `discover` via
  `asyncio.to_thread` (orchestrator does this). Prefer `JOBSPY_PYTHON` pointing
  at a dedicated 3.12 venv so the API stays on 3.14 while JobSpy stays stable.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings

_SCRAPER = Path(__file__).with_name("_jobspy_scrape_worker.py")


def _worker_python() -> str:
    configured = (settings.JOBSPY_PYTHON or "").strip()
    if configured:
        return configured
    return sys.executable


class JobSpyProvider:
    name = "jobspy"

    def __init__(self) -> None:
        self.last_error: str | None = None

    def discover(
        self,
        *,
        query: str,
        location: str | None,
        limit: int,
        sites: list[str] | None = None,
        hours_old: int | None = None,
        country_indeed: str = "USA",
    ) -> list[dict[str, Any]]:
        """Blocking scrape — always invoke from a worker thread, not the event loop."""
        self.last_error = None
        site_name = sites or ["indeed"]
        payload = {
            "query": query,
            "location": location,
            "limit": int(limit),
            "sites": site_name,
            "hours_old": hours_old,
            "country_indeed": country_indeed,
        }
        python_bin = _worker_python()

        # System HTTP(S)_PROXY (e.g. 127.0.0.1:1080) often points at a local
        # VPN that is down — JobSpy then fails with ProxyError while direct
        # Indeed access works. Prefer a clean env for the scrape child.
        child_env = {
            k: v
            for k, v in __import__("os").environ.items()
            if k.upper()
            not in {
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            }
        }

        with tempfile.TemporaryDirectory(prefix="jobspy_") as tmp:
            in_path = Path(tmp) / "in.json"
            out_path = Path(tmp) / "out.json"
            in_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                proc = subprocess.run(
                    [python_bin, str(_SCRAPER), str(in_path), str(out_path)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                    env=child_env,
                )
            except subprocess.TimeoutExpired:
                self.last_error = "scrape_timeout_120s"
                return []
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"subprocess_failed: {exc}"
                return []

            if proc.returncode != 0:
                err_tail = (proc.stderr or proc.stdout or "").strip()[-400:]
                # Worker may still write a JSON error payload on non-zero exit.
                if out_path.exists():
                    try:
                        data = json.loads(out_path.read_text(encoding="utf-8"))
                        if data.get("error"):
                            self.last_error = str(data["error"])
                            return []
                    except Exception:  # noqa: BLE001
                        pass
                self.last_error = f"scrape_exit_{proc.returncode}: {err_tail or 'no_stderr'}"
                return []

            if not out_path.exists():
                self.last_error = "missing_output"
                return []

            try:
                data = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"bad_output: {exc}"
                return []

            if data.get("error"):
                self.last_error = str(data["error"])
                return []

            jobs = data.get("jobs") or []
            if not jobs:
                self.last_error = "empty_result"
            return jobs
