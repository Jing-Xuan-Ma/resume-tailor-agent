"""Small persistent storage layer for the MVP.

The project still uses Chroma for semantic memory. This module stores durable
application state that must survive backend restarts: users, drafts, tailored
resumes, conversations, events, user profiles, and discovered jobs.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _PROJECT_ROOT / "data" / "app.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_INITIALIZED = False


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    global _INITIALIZED
    if not _INITIALIZED:
        init_db()
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tailored_resumes (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                resume_id TEXT NOT NULL,
                job_id TEXT,
                jd_text TEXT NOT NULL,
                jd_parsed_json TEXT NOT NULL,
                tailored_resume_json TEXT NOT NULL,
                markdown TEXT NOT NULL,
                key_map_json TEXT NOT NULL,
                ats_score_estimate REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                resume_id TEXT NOT NULL,
                tailored_resume_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_turns (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                source_url TEXT,
                source_platform TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                match_score REAL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_bookmarks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, job_id)
            );

            CREATE TABLE IF NOT EXISTS application_runs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                tailored_resume_id TEXT,
                status TEXT NOT NULL,
                ats_type TEXT NOT NULL,
                submit_mode TEXT NOT NULL DEFAULT 'manual_review',
                plan_json TEXT NOT NULL,
                answers_json TEXT NOT NULL,
                submission_result_json TEXT NOT NULL DEFAULT '{}',
                submitted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cover_letters (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                tailored_resume_id TEXT,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS application_audit_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                application_run_id TEXT,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tailored_user ON tailored_resumes(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id, updated_at);
            CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_turns(user_id, session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON job_bookmarks(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_application_runs_user ON application_runs(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_cover_letters_user ON cover_letters(user_id, created_at);
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(application_runs)").fetchall()}
        if "submit_mode" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submit_mode TEXT NOT NULL DEFAULT 'manual_review'")
        if "submission_result_json" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submission_result_json TEXT NOT NULL DEFAULT '{}'")
        if "submitted_at" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submitted_at TEXT")
        conn.commit()
    finally:
        conn.close()
    _INITIALIZED = True


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def create_user(email: str, full_name: str, password_hash: str) -> dict[str, Any]:
    now = utcnow()
    user_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, full_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email.lower(), full_name, password_hash, now, now),
        )
    return {"id": user_id, "email": email.lower(), "full_name": full_name, "created_at": now, "updated_at": now}


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return dict(row) if row else None


def get_user(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def save_tailored_resume(
    *,
    user_id: str,
    resume_id: str,
    job_id: str | None,
    jd_text: str,
    jd_parsed: dict,
    tailored_resume: dict,
    markdown: str,
    key_map: list[dict],
) -> str:
    now = utcnow()
    tailored_id = str(uuid4())
    ats_score = tailored_resume.get("ats_score_estimate") if isinstance(tailored_resume, dict) else None
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tailored_resumes
            (id, user_id, resume_id, job_id, jd_text, jd_parsed_json, tailored_resume_json, markdown, key_map_json, ats_score_estimate, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tailored_id,
                user_id,
                resume_id,
                job_id,
                jd_text,
                _json(jd_parsed),
                _json(tailored_resume),
                markdown,
                _json(key_map),
                ats_score,
                now,
                now,
            ),
        )
    return tailored_id


def get_tailored_resume(tailored_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM tailored_resumes WHERE id = ?"
    params: tuple[Any, ...] = (tailored_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (tailored_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    data = dict(row)
    data["jd_parsed"] = _loads(data.pop("jd_parsed_json"), {})
    data["tailored_resume"] = _loads(data.pop("tailored_resume_json"), {})
    data["key_map"] = _loads(data.pop("key_map_json"), [])
    return data


def save_draft(draft: dict[str, Any], tailored_resume_id: str | None = None) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO drafts (id, user_id, resume_id, tailored_resume_id, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at,
                tailored_resume_id = COALESCE(excluded.tailored_resume_id, drafts.tailored_resume_id)
            """,
            (
                draft["draft_id"],
                draft["user_id"],
                draft["resume_id"],
                tailored_resume_id,
                _json(draft),
                draft.get("created_at", now),
                now,
            ),
        )


def get_draft(draft_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT payload_json FROM drafts WHERE id = ?"
    params: tuple[Any, ...] = (draft_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (draft_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    return _loads(row["payload_json"], None) if row else None


def save_conversation_turn(user_id: str, session_id: str, role: str, content: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversation_turns (id, user_id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, session_id, role, content, utcnow()),
        )


def save_profile(user_id: str, profile: dict[str, Any]) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO user_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at
            """,
            (user_id, _json(profile), now),
        )


def get_profile(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    return _loads(row["profile_json"], None) if row else None


def save_event(event_type: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid4()), event_type, _json(payload), utcnow()),
        )


def save_job(*, user_id: str, title: str, company: str | None, location: str | None, source_url: str | None,
             source_platform: str, raw_text: str, parsed: dict, match_score: float | None) -> str:
    job_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, user_id, title, company, location, source_url, source_platform, raw_text, parsed_json, match_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, user_id, title, company, location, source_url, source_platform, raw_text, _json(parsed), match_score, utcnow()),
        )
    return job_id


def get_job(job_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM jobs WHERE id = ?"
    params: tuple[Any, ...] = (job_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (job_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["parsed"] = _loads(item.pop("parsed_json"), {})
    return item


def list_jobs(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["parsed"] = _loads(item.pop("parsed_json"), {})
        jobs.append(item)
    return jobs


def bookmark_job(user_id: str, job_id: str, notes: str | None = None) -> dict[str, Any]:
    bookmark_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO job_bookmarks (id, user_id, job_id, notes, created_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, job_id) DO UPDATE SET notes = excluded.notes
            """,
            (bookmark_id, user_id, job_id, notes, now),
        )
        row = conn.execute(
            "SELECT * FROM job_bookmarks WHERE user_id = ? AND job_id = ?",
            (user_id, job_id),
        ).fetchone()
    return dict(row)


def list_bookmarked_jobs(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT j.*, b.id AS bookmark_id, b.notes AS bookmark_notes, b.created_at AS bookmarked_at
            FROM job_bookmarks b
            JOIN jobs j ON j.id = b.job_id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["parsed"] = _loads(item.pop("parsed_json"), {})
        jobs.append(item)
    return jobs


def save_application_run(*, user_id: str, job_id: str, tailored_resume_id: str | None, status: str,
                         ats_type: str, plan: dict, answers: list[dict], submit_mode: str = "manual_review") -> str:
    run_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO application_runs
            (id, user_id, job_id, tailored_resume_id, status, ats_type, submit_mode, plan_json, answers_json, submission_result_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, user_id, job_id, tailored_resume_id, status, ats_type, submit_mode, _json(plan), _json(answers), _json({}), now, now),
        )
    return run_id


def update_application_run_status(*, run_id: str, user_id: str, status: str, submission_result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    now = utcnow()
    submitted_at = now if status in {"submitted_by_user", "auto_submitted"} else None
    with connect() as conn:
        conn.execute(
            """
            UPDATE application_runs
            SET status = ?, submission_result_json = ?, submitted_at = COALESCE(?, submitted_at), updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, _json(submission_result or {}), submitted_at, now, run_id, user_id),
        )
    return get_application_run(run_id, user_id=user_id)


def get_application_run(run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM application_runs WHERE id = ?"
    params: tuple[Any, ...] = (run_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (run_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["plan"] = _loads(item.pop("plan_json"), {})
    item["answers"] = _loads(item.pop("answers_json"), [])
    item["submission_result"] = _loads(item.pop("submission_result_json", None), {})
    return item


def list_application_runs(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM application_runs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    runs = []
    for row in rows:
        item = dict(row)
        item["plan"] = _loads(item.pop("plan_json"), {})
        item["answers"] = _loads(item.pop("answers_json"), [])
        item["submission_result"] = _loads(item.pop("submission_result_json", None), {})
        runs.append(item)
    return runs


def save_application_audit(user_id: str, application_run_id: str | None, action: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO application_audit_logs (id, user_id, application_run_id, action, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), user_id, application_run_id, action, _json(payload), utcnow()),
        )


def save_cover_letter(*, user_id: str, job_id: str, tailored_resume_id: str | None, text: str, metadata: dict[str, Any]) -> str:
    cover_letter_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO cover_letters (id, user_id, job_id, tailored_resume_id, text, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cover_letter_id, user_id, job_id, tailored_resume_id, text, _json(metadata), utcnow()),
        )
    return cover_letter_id


def get_cover_letter(cover_letter_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM cover_letters WHERE id = ?"
    params: tuple[Any, ...] = (cover_letter_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (cover_letter_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = _loads(item.pop("metadata_json"), {})
    return item
