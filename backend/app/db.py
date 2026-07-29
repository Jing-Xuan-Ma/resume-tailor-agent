"""Persistent storage layer — supports SQLite (local dev) and PostgreSQL (production).

Auto-detects the database type from DATABASE_URL:
  - sqlite:///… → uses sqlite3
  - postgresql://… → uses psycopg2

Data export/import scripts in scripts/ help migrate between the two.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from app.config import settings


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _PROJECT_ROOT / "data" / "app.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_INITIALIZED = False
_PG_CONN_PARAMS: dict[str, Any] | None = None


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# PostgreSQL detection & connection helpers
# ---------------------------------------------------------------------------

def _is_pg() -> bool:
    url = (settings.DATABASE_URL or "").strip()
    return url.startswith("postgresql://")


def _parse_pg_url(url: str) -> dict[str, Any]:
    rest = url.split("://", 1)[1] if "://" in url else url
    user_pass, rest = rest.split("@", 1) if "@" in rest else ("", rest)
    user = ""
    password = ""
    if ":" in user_pass:
        user, password = user_pass.split(":", 1)
    elif user_pass:
        user = user_pass
    host_port, dbname = rest.split("/", 1) if "/" in rest else (rest, "")
    host = host_port
    port = 5432
    if ":" in host_port:
        host, port_str = host_port.split(":", 1)
        port = int(port_str)
    return {
        "host": host or "localhost",
        "port": port,
        "dbname": dbname or "resume_agent",
        "user": user or "resume_agent",
        "password": password,
    }


def _get_pg_conn() -> Any:
    global _PG_CONN_PARAMS
    if _PG_CONN_PARAMS is None:
        _PG_CONN_PARAMS = _parse_pg_url(settings.DATABASE_URL)
    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(**_PG_CONN_PARAMS)
        conn.autocommit = False
        return conn
    except Exception as e:
        raise RuntimeError(f"PostgreSQL connection failed: {e}")


# ---------------------------------------------------------------------------
# Schema (shared between SQLite & PG; PG uses BYTEA, SQLite uses BLOB)
# ---------------------------------------------------------------------------

PG_SCHEMA_SQL = """
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
CREATE TABLE IF NOT EXISTS resumes (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    filename TEXT,
    raw_text TEXT,
    parsed_json TEXT NOT NULL,
    embedded_count INTEGER NOT NULL DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS outreach_messages (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT,
    contact_name TEXT,
    contact_role TEXT,
    company TEXT,
    channel TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    unsubscribe_token TEXT,
    sent_at TEXT,
    delivery_status TEXT,
    delivery_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS growth_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT,
    target_role TEXT NOT NULL,
    gaps_json TEXT NOT NULL,
    recommendations_json TEXT NOT NULL,
    roadmap_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tailored_user ON tailored_resumes(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_resumes_user ON resumes(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_turns(user_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bookmarks_user ON job_bookmarks(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_application_runs_user ON application_runs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_cover_letters_user ON cover_letters(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_outreach_user ON outreach_messages(user_id, created_at);
CREATE TABLE IF NOT EXISTS job_history (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    action TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jd_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_id TEXT,
    jd_text TEXT NOT NULL,
    keyword_matches_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resume_versions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    version_index INTEGER NOT NULL,
    content_delta_json TEXT NOT NULL,
    full_resume_json TEXT NOT NULL,
    markdown TEXT NOT NULL DEFAULT '',
    is_confirmed INTEGER NOT NULL DEFAULT 0,
    confirmed_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resume_templates (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    docx_bytes BYTEA,
    parsed_blocks_json TEXT NOT NULL DEFAULT '[]',
    is_active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_growth_user ON growth_plans(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_job_history_user_job ON job_history(user_id, job_id);
CREATE INDEX IF NOT EXISTS idx_jd_sessions_user ON jd_sessions(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_resume_versions_session ON resume_versions(session_id, version_index);
CREATE INDEX IF NOT EXISTS idx_resume_templates_user ON resume_templates(user_id, is_active);
"""

# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def _init_pg_schema() -> None:
    global _INITIALIZED, _db_connection
    if _INITIALIZED:
        return
    conn = _get_pg_conn()
    try:
        cur = conn.cursor()
        for statement in PG_SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                cur.execute(stmt + ";")
        conn.commit()
        _INITIALIZED = True
        _db_connection = _get_pg_conn
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Failed to initialize PostgreSQL schema: {e}")
    finally:
        conn.close()


def init_db() -> None:
    global _INITIALIZED, _db_connection
    if _INITIALIZED:
        return
    if _is_pg():
        _init_pg_schema()
        return

    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.executescript(
            PG_SCHEMA_SQL
            .replace("BYTEA", "BLOB")
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(application_runs)").fetchall()}
        if "submit_mode" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submit_mode TEXT NOT NULL DEFAULT 'manual_review'")
        if "submission_result_json" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submission_result_json TEXT NOT NULL DEFAULT '{}'")
        if "submitted_at" not in columns:
            conn.execute("ALTER TABLE application_runs ADD COLUMN submitted_at TEXT")
        conn.commit()
        _INITIALIZED = True
        _db_connection = lambda: sqlite3.connect(str(_DB_PATH))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Connection context manager — dual-mode
# ---------------------------------------------------------------------------

_db_connection: Any | None = None


@contextmanager
def connect() -> Iterator[Any]:
    global _INITIALIZED, _db_connection
    if not _INITIALIZED:
        if _is_pg():
            _init_pg_schema()
            _db_connection = _get_pg_conn
        else:
            init_db()
            _db_connection = lambda: sqlite3.connect(str(_DB_PATH))

    if _is_pg():
        conn = _get_pg_conn()
        try:
            from psycopg2.extras import RealDictCursor
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            yield cursor
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = _db_connection()
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Resume CRUD
# ---------------------------------------------------------------------------

def save_resume(
    *,
    user_id: str,
    source_type: str,
    filename: str | None = None,
    raw_text: str | None = None,
    parsed: dict[str, Any] | None = None,
    embedded_count: int = 0,
) -> str:
    now = utcnow()
    resume_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO resumes (id, user_id, source_type, filename, raw_text, parsed_json, embedded_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (resume_id, user_id, source_type, filename, raw_text, _json(parsed or {}), embedded_count, now, now),
        )
    return resume_id


def get_resume(resume_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM resumes WHERE id = ?"
    params: tuple[Any, ...] = (resume_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (resume_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["parsed"] = _loads(item.pop("parsed_json"), {})
    return item


def get_latest_resume(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM resumes WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["parsed"] = _loads(item.pop("parsed_json"), {})
    return item


# ---------------------------------------------------------------------------
# Tailored Resume CRUD
# ---------------------------------------------------------------------------

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
            "INSERT INTO tailored_resumes (id, user_id, resume_id, job_id, jd_text, jd_parsed_json, tailored_resume_json, markdown, key_map_json, ats_score_estimate, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tailored_id, user_id, resume_id, job_id, jd_text, _json(jd_parsed), _json(tailored_resume), markdown, _json(key_map), ats_score, now, now),
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


# ---------------------------------------------------------------------------
# Draft CRUD
# ---------------------------------------------------------------------------

def save_draft(draft: dict[str, Any], tailored_resume_id: str | None = None) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO drafts (id, user_id, resume_id, tailored_resume_id, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at, tailored_resume_id = COALESCE(excluded.tailored_resume_id, drafts.tailored_resume_id)",
            (draft["draft_id"], draft["user_id"], draft["resume_id"], tailored_resume_id, _json(draft), draft.get("created_at", now), now),
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


# ---------------------------------------------------------------------------
# Conversation CRUD
# ---------------------------------------------------------------------------

def save_conversation_turn(user_id: str, session_id: str, role: str, content: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO conversation_turns (id, user_id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, session_id, role, content, utcnow()),
        )


# ---------------------------------------------------------------------------
# User Profile CRUD
# ---------------------------------------------------------------------------

def save_profile(user_id: str, profile: dict[str, Any]) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO user_profiles (user_id, profile_json, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json, updated_at = excluded.updated_at",
            (user_id, _json(profile), now),
        )


def get_profile(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT profile_json FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
    return _loads(row["profile_json"], None) if row else None


# ---------------------------------------------------------------------------
# Event / Audit Log
# ---------------------------------------------------------------------------

def save_event(event_type: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid4()), event_type, _json(payload), utcnow()),
        )


def save_application_audit(user_id: str, application_run_id: str | None, action: str, payload: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO application_audit_logs (id, user_id, application_run_id, action, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, application_run_id, action, _json(payload), utcnow()),
        )


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

def save_job(*, user_id: str, title: str, company: str | None, location: str | None, source_url: str | None,
             source_platform: str, raw_text: str, parsed: dict, match_score: float | None) -> str:
    job_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, user_id, title, company, location, source_url, source_platform, raw_text, parsed_json, match_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


# ---------------------------------------------------------------------------
# Job Bookmark CRUD
# ---------------------------------------------------------------------------

def bookmark_job(user_id: str, job_id: str, notes: str | None = None) -> dict[str, Any]:
    bookmark_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_bookmarks (id, user_id, job_id, notes, created_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(user_id, job_id) DO UPDATE SET notes = excluded.notes",
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
            "SELECT j.*, b.id AS bookmark_id, b.notes AS bookmark_notes, b.created_at AS bookmarked_at FROM job_bookmarks b JOIN jobs j ON j.id = b.job_id WHERE b.user_id = ? ORDER BY b.created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["parsed"] = _loads(item.pop("parsed_json"), {})
        jobs.append(item)
    return jobs


# ---------------------------------------------------------------------------
# Application Run CRUD
# ---------------------------------------------------------------------------

def save_application_run(*, user_id: str, job_id: str, tailored_resume_id: str | None, status: str,
                         ats_type: str, plan: dict, answers: list[dict], submit_mode: str = "manual_review") -> str:
    run_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO application_runs (id, user_id, job_id, tailored_resume_id, status, ats_type, submit_mode, plan_json, answers_json, submission_result_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, user_id, job_id, tailored_resume_id, status, ats_type, submit_mode, _json(plan), _json(answers), _json({}), now, now),
        )
    return run_id


def update_application_run_status(*, run_id: str, user_id: str, status: str, submission_result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    now = utcnow()
    submitted_at = now if status in {"submitted_by_user", "auto_submitted"} else None
    with connect() as conn:
        conn.execute(
            "UPDATE application_runs SET status = ?, submission_result_json = ?, submitted_at = COALESCE(?, submitted_at), updated_at = ? WHERE id = ? AND user_id = ?",
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


# ---------------------------------------------------------------------------
# Cover Letter CRUD
# ---------------------------------------------------------------------------

def save_cover_letter(*, user_id: str, job_id: str, tailored_resume_id: str | None, text: str, metadata: dict[str, Any]) -> str:
    cover_letter_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO cover_letters (id, user_id, job_id, tailored_resume_id, text, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
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


# ---------------------------------------------------------------------------
# Outreach Message CRUD
# ---------------------------------------------------------------------------

def save_outreach_message(
    *,
    message_id: str | None = None,
    user_id: str,
    job_id: str | None,
    contact_name: str | None,
    contact_role: str | None,
    company: str | None,
    channel: str,
    subject: str,
    body: str,
    status: str = "draft",
    metadata: dict[str, Any] | None = None,
    unsubscribe_token: str | None = None,
) -> str:
    message_id = message_id or str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO outreach_messages (id, user_id, job_id, contact_name, contact_role, company, channel, subject, body, status, metadata_json, unsubscribe_token, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, user_id, job_id, contact_name, contact_role, company, channel, subject, body, status, _json(metadata or {}), unsubscribe_token, now, now),
        )
    return message_id


def update_outreach_send_status(message_id: str, user_id: str, delivery_status: str, delivery_error: str | None = None) -> dict[str, Any] | None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "UPDATE outreach_messages SET status = ?, delivery_status = ?, delivery_error = ?, sent_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            ("sent", delivery_status, delivery_error, now, now, message_id, user_id),
        )
    return get_outreach_message(message_id, user_id=user_id)


def get_outreach_by_unsubscribe_token(token: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM outreach_messages WHERE unsubscribe_token = ?",
            (token,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = _loads(item.pop("metadata_json"), {})
    return item


def mark_outreach_unsubscribed(token: str) -> bool:
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE outreach_messages SET status = 'unsubscribed', updated_at = ? WHERE unsubscribe_token = ?",
            (utcnow(), token),
        )
        return cursor.rowcount > 0


def update_outreach_status(message_id: str, user_id: str, status: str) -> dict[str, Any] | None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "UPDATE outreach_messages SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (status, now, message_id, user_id),
        )
    return get_outreach_message(message_id, user_id=user_id)


def get_outreach_message(message_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM outreach_messages WHERE id = ?"
    params: tuple[Any, ...] = (message_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (message_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["metadata"] = _loads(item.pop("metadata_json"), {})
    return item


def list_outreach_messages(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM outreach_messages WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    messages = []
    for row in rows:
        item = dict(row)
        item["metadata"] = _loads(item.pop("metadata_json"), {})
        messages.append(item)
    return messages


# ---------------------------------------------------------------------------
# Growth Plan CRUD
# ---------------------------------------------------------------------------

def save_growth_plan(
    *,
    user_id: str,
    job_id: str | None,
    target_role: str,
    gaps: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
) -> str:
    plan_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO growth_plans (id, user_id, job_id, target_role, gaps_json, recommendations_json, roadmap_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (plan_id, user_id, job_id, target_role, _json(gaps), _json(recommendations), _json(roadmap), utcnow()),
        )
    return plan_id


def list_growth_plans(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM growth_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    plans = []
    for row in rows:
        item = dict(row)
        item["gaps"] = _loads(item.pop("gaps_json"), [])
        item["recommendations"] = _loads(item.pop("recommendations_json"), [])
        item["roadmap"] = _loads(item.pop("roadmap_json"), [])
        plans.append(item)
    return plans


# ---------------------------------------------------------------------------
# Job History / Actions
# ---------------------------------------------------------------------------

def record_job_action(user_id: str, job_id: str, action: str, metadata: dict | None = None) -> str:
    record_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO job_history (id, user_id, job_id, action, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (record_id, user_id, job_id, action, _json(metadata or {}), utcnow()),
        )
    return record_id


def get_job_actions(user_id: str, job_id: str | None = None) -> list[dict[str, Any]]:
    if job_id:
        query = "SELECT * FROM job_history WHERE user_id = ? AND job_id = ? ORDER BY created_at DESC"
        params: tuple = (user_id, job_id)
    else:
        query = "SELECT * FROM job_history WHERE user_id = ? ORDER BY created_at DESC"
        params = (user_id,)
    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def list_processed_job_ids(user_id: str) -> set[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT job_id FROM job_history WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return {r["job_id"] for r in rows}


def list_job_history_with_details(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT jh.*, j.title, j.company, j.location, j.source_platform, j.match_score, j.created_at AS job_created_at FROM job_history jh LEFT JOIN jobs j ON j.id = jh.job_id WHERE jh.user_id = ? ORDER BY jh.created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# JD Session CRUD
# ---------------------------------------------------------------------------

def create_jd_session(*, user_id: str, job_id: str | None = None, jd_text: str) -> dict[str, Any]:
    session_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "INSERT INTO jd_sessions (id, user_id, job_id, jd_text, keyword_matches_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, user_id, job_id, jd_text, _json([]), now, now),
        )
    return {"id": session_id, "user_id": user_id, "job_id": job_id, "jd_text": jd_text, "keyword_matches": [], "created_at": now, "updated_at": now}


def get_jd_session(session_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM jd_sessions WHERE id = ?"
    params: tuple[Any, ...] = (session_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (session_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["keyword_matches"] = _loads(item.pop("keyword_matches_json"), [])
    return item


def update_jd_session_keywords(session_id: str, keyword_matches: list[dict]) -> None:
    now = utcnow()
    with connect() as conn:
        conn.execute(
            "UPDATE jd_sessions SET keyword_matches_json = ?, updated_at = ? WHERE id = ?",
            (_json(keyword_matches), now, session_id),
        )


# ---------------------------------------------------------------------------
# Resume Version CRUD
# ---------------------------------------------------------------------------

def create_resume_version(*, session_id: str, user_id: str, version_index: int, content_delta: dict, full_resume: dict, markdown: str = "") -> str:
    version_id = str(uuid4())
    with connect() as conn:
        conn.execute(
            "INSERT INTO resume_versions (id, session_id, user_id, version_index, content_delta_json, full_resume_json, markdown, is_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (version_id, session_id, user_id, version_index, _json(content_delta), _json(full_resume), markdown, utcnow()),
        )
    return version_id


def confirm_resume_version(version_id: str, user_id: str) -> bool:
    now = utcnow()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE resume_versions SET is_confirmed = 1, confirmed_at = ? WHERE id = ? AND user_id = ?",
            (now, version_id, user_id),
        )
        return cursor.rowcount > 0


def get_resume_version(version_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query = "SELECT * FROM resume_versions WHERE id = ?"
    params: tuple[Any, ...] = (version_id,)
    if user_id:
        query += " AND user_id = ?"
        params = (version_id, user_id)
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    item = dict(row)
    item["content_delta"] = _loads(item.pop("content_delta_json"), {})
    item["full_resume"] = _loads(item.pop("full_resume_json"), {})
    return item


def list_resume_versions(session_id: str, user_id: str) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM resume_versions WHERE session_id = ? AND user_id = ? ORDER BY version_index ASC",
            (session_id, user_id),
        ).fetchall()
    versions = []
    for row in rows:
        item = dict(row)
        item["content_delta"] = _loads(item.pop("content_delta_json"), {})
        item["full_resume"] = _loads(item.pop("full_resume_json"), {})
        versions.append(item)
    return versions


def get_latest_version_index(session_id: str, user_id: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version_index), 0) AS max_idx FROM resume_versions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
    return row["max_idx"] if row else 0


def delete_oldest_version(session_id: str, user_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "DELETE FROM resume_versions WHERE id = (SELECT id FROM resume_versions WHERE session_id = ? AND user_id = ? ORDER BY version_index ASC LIMIT 1)",
            (session_id, user_id),
        )


# ---------------------------------------------------------------------------
# Resume Template CRUD
# ---------------------------------------------------------------------------

def save_template(*, user_id: str, filename: str, docx_bytes: bytes, parsed_blocks: list[dict]) -> str:
    template_id = str(uuid4())
    now = utcnow()
    with connect() as conn:
        conn.execute("UPDATE resume_templates SET is_active = 0 WHERE user_id = ?", (user_id,))
        conn.execute(
            "INSERT INTO resume_templates (id, user_id, filename, docx_bytes, parsed_blocks_json, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (template_id, user_id, filename, docx_bytes, _json(parsed_blocks), now, now),
        )
    return template_id


def get_active_template(user_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM resume_templates WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["parsed_blocks"] = _loads(item.pop("parsed_blocks_json"), [])
    return item


def get_template(template_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM resume_templates WHERE id = ?",
            (template_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["parsed_blocks"] = _loads(item.pop("parsed_blocks_json"), [])
    return item
