"""
In-memory resume draft store for the MVP.

This keeps the latest generated resume, JD mapping, markdown export, and revision
history available to chat-driven edits without introducing a database migration.
"""

from datetime import UTC, datetime
from uuid import uuid4


class ResumeDraftStore:
    def __init__(self):
        self._drafts: dict[str, dict] = {}

    def create(
        self,
        *,
        user_id: str,
        resume_id: str,
        jd_text: str,
        jd_parsed: dict,
        tailored_resume: dict,
        markdown: str,
        key_map: list[dict],
    ) -> dict:
        draft_id = str(uuid4())
        revision_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        draft = {
            "draft_id": draft_id,
            "user_id": user_id,
            "resume_id": resume_id,
            "jd_text": jd_text,
            "jd_parsed": jd_parsed,
            "tailored_resume": tailored_resume,
            "markdown": markdown,
            "key_map": key_map,
            "current_revision_id": revision_id,
            "created_at": now,
            "updated_at": now,
            "revisions": [
                {
                    "revision_id": revision_id,
                    "instruction": "Initial tailored resume",
                    "tailored_resume": tailored_resume,
                    "markdown": markdown,
                    "key_map": key_map,
                    "created_at": now,
                }
            ],
        }
        self._drafts[draft_id] = draft
        return draft

    def get(self, draft_id: str) -> dict | None:
        return self._drafts.get(draft_id)

    def update(
        self,
        *,
        draft_id: str,
        instruction: str,
        tailored_resume: dict,
        markdown: str,
        key_map: list[dict],
    ) -> dict:
        draft = self._drafts[draft_id]
        revision_id = str(uuid4())
        now = datetime.now(UTC).isoformat()
        revision = {
            "revision_id": revision_id,
            "instruction": instruction,
            "tailored_resume": tailored_resume,
            "markdown": markdown,
            "key_map": key_map,
            "created_at": now,
        }
        draft["tailored_resume"] = tailored_resume
        draft["markdown"] = markdown
        draft["key_map"] = key_map
        draft["current_revision_id"] = revision_id
        draft["updated_at"] = now
        draft["revisions"].append(revision)
        return draft


draft_store = ResumeDraftStore()
