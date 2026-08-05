"""Initial schema — all 19 tables + indexes.

Revision ID: 0001
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    try:
        conn = op.get_bind()
        inspector = Inspector.from_engine(conn)
        return name in inspector.get_table_names()
    except Exception:
        return False  # offline mode — assume table doesn't exist


def upgrade() -> None:
    if _has_table("users"):
        return  # already applied

    # ── users ────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # ── tailored_resumes ─────────────────────────────────────
    op.create_table(
        "tailored_resumes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("resume_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("jd_parsed_json", sa.Text(), nullable=False),
        sa.Column("tailored_resume_json", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("key_map_json", sa.Text(), nullable=False),
        sa.Column("ats_score_estimate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tailored_user", "tailored_resumes", ["user_id", "created_at"])

    # ── resumes ──────────────────────────────────────────────
    op.create_table(
        "resumes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("parsed_json", sa.Text(), nullable=False),
        sa.Column("embedded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_resumes_user", "resumes", ["user_id", "updated_at"])

    # ── drafts ───────────────────────────────────────────────
    op.create_table(
        "drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("resume_id", sa.String(), nullable=False),
        sa.Column("tailored_resume_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_drafts_user", "drafts", ["user_id", "updated_at"])

    # ── conversation_turns ───────────────────────────────────
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_conversation_session", "conversation_turns", ["user_id", "session_id", "created_at"])

    # ── user_profiles ────────────────────────────────────────
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ── events ──────────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── jobs ───────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("source_platform", sa.String(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_json", sa.Text(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_jobs_user", "jobs", ["user_id", "created_at"])

    # ── job_bookmarks ─────────────────────────────────────
    op.create_table(
        "job_bookmarks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_id"),
    )
    op.create_index("idx_bookmarks_user", "job_bookmarks", ["user_id", "created_at"])

    # ── application_runs ─────────────────────────────────
    op.create_table(
        "application_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("tailored_resume_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ats_type", sa.String(), nullable=False),
        sa.Column("submit_mode", sa.String(), server_default="manual_review", nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("answers_json", sa.Text(), nullable=False),
        sa.Column("submission_result_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("submitted_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_application_runs_user", "application_runs", ["user_id", "created_at"])

    # ── cover_letters ───────────────────────────────────
    op.create_table(
        "cover_letters",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("tailored_resume_id", sa.String(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_cover_letters_user", "cover_letters", ["user_id", "created_at"])

    # ── application_audit_logs ─────────────────────────
    op.create_table(
        "application_audit_logs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("application_run_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── outreach_messages ──────────────────────────────
    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("contact_name", sa.String(), nullable=True),
        sa.Column("contact_role", sa.String(), nullable=True),
        sa.Column("company", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("metadata_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("unsubscribe_token", sa.String(), nullable=True),
        sa.Column("sent_at", sa.String(), nullable=True),
        sa.Column("delivery_status", sa.String(), nullable=True),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_outreach_user", "outreach_messages", ["user_id", "created_at"])

    # ── growth_plans ─────────────────────────────────
    op.create_table(
        "growth_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("target_role", sa.String(), nullable=False),
        sa.Column("gaps_json", sa.Text(), nullable=False),
        sa.Column("recommendations_json", sa.Text(), nullable=False),
        sa.Column("roadmap_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_growth_user", "growth_plans", ["user_id", "created_at"])

    # ── job_history ───────────────────────────────────
    op.create_table(
        "job_history",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("metadata", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_history_user_job", "job_history", ["user_id", "job_id"])

    # ── jd_sessions ─────────────────────────────────
    op.create_table(
        "jd_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=False),
        sa.Column("keyword_matches_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_jd_sessions_user", "jd_sessions", ["user_id", "created_at"])

    # ── resume_versions ──────────────────────────────
    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("version_index", sa.Integer(), nullable=False),
        sa.Column("content_delta_json", sa.Text(), nullable=False),
        sa.Column("full_resume_json", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), server_default="", nullable=False),
        sa.Column("is_confirmed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confirmed_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_resume_versions_session", "resume_versions", ["session_id", "version_index"])

    # ── resume_templates ─────────────────────────────
    op.create_table(
        "resume_templates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("docx_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("parsed_blocks_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_resume_templates_user", "resume_templates", ["user_id", "is_active"])


def downgrade() -> None:
    tables = [
        "resume_templates",
        "resume_versions",
        "jd_sessions",
        "job_history",
        "growth_plans",
        "outreach_messages",
        "application_audit_logs",
        "cover_letters",
        "application_runs",
        "job_bookmarks",
        "jobs",
        "events",
        "user_profiles",
        "conversation_turns",
        "drafts",
        "resumes",
        "tailored_resumes",
        "users",
    ]
    for table in tables:
        op.drop_table(table)
