# JobSpy on Python 3.12 (2026-08-03)

## Why subprocess isolation

JobSpy (via pinned numpy) can **hard-crash** the interpreter on Windows **Python 3.14** (`ACCESS_VIOLATION`). That kills the whole uvicorn process — every API route dies with it.

Subprocess isolation means: scrape runs in a **child** process. If JobSpy segfaults, only the child dies; the API parent stays up and records `last_error`.

## Why isolation can still drag the API

Isolation stops *crashes*, not *blocking*.

A sync `subprocess.run(..., timeout=90)` inside an async coroutine pins the asyncio event loop for the full scrape. During that window other HTTP requests stall.

**Fix:** keep the child process (crash safety + 3.12 worker), but run `discover` via `asyncio.to_thread` in `orchestrator.py`.

## Setup that works

| Piece | Value |
|-------|--------|
| API venv | `backend/venv` (Python 3.14) — **do not** install `python-jobspy` here |
| JobSpy venv | `backend/venv312` (Python 3.12.10 + `python-jobspy==1.1.82`) |
| Config | `JOB_INDEX_ENABLE_JOBSPY=true` |
| Worker | `JOBSPY_PYTHON=d:/resume-agent/backend/venv312/Scripts/python.exe` |

## Verified

- Worker smoke: 5 Indeed jobs in ~10s on 3.12
- `discover_all` with JobSpy: `jobspy.count=5`, parent alive
- Live `POST /api/v1/jobs/index/ingest`: `provider_stats.jobspy.count=8`, API still serving
