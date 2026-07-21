"""
Experience Embedder — Splits a user's resume into searchable document chunks
and persists them into the long-term vector store.
"""

from typing import List

from app.core.models import Experience, Resume
from app.memory.long_term import LongTermMemoryStore


class ExperienceEmbedder:
    """
    Converts structured resume experiences into embedding documents
    and stores them in Chroma for semantic retrieval.
    """

    def __init__(self, store: LongTermMemoryStore | None = None):
        self.store = store or LongTermMemoryStore()

    def _experience_to_documents(self, experience: Experience) -> list[dict]:
        """
        Turn a single Experience into one or more searchable documents.
        Each bullet becomes its own document for fine-grained retrieval.
        """
        base_meta = {
            "experience_id": str(experience.id),
            "company": experience.company,
            "title": experience.title,
            "date_range": experience.date_range,
            "type": "experience",
        }

        documents = []

        # 1. Add a summary document for the whole experience
        summary_text = (
            f"{experience.title} at {experience.company}. "
            f"{experience.summary or ''} "
            f"Skills: {', '.join(experience.skills)}."
        ).strip()

        documents.append({
            "text": summary_text,
            "metadata": {**base_meta, "chunk_type": "summary"},
        })

        # 2. Add each bullet as its own document
        for idx, bullet in enumerate(experience.bullets):
            documents.append({
                "text": bullet.text,
                "metadata": {
                    **base_meta,
                    "chunk_type": "bullet",
                    "bullet_index": idx,
                    "mentioned_skills": bullet.mentioned_skills,
                    "metrics": bullet.metrics,
                },
            })

        return documents

    async def embed_resume(self, user_id: str, resume: Resume) -> int:
        """
        Embed all experiences from a resume into the vector store.
        Returns the number of documents embedded.
        """
        all_documents: List[dict] = []
        for exp in resume.experiences:
            all_documents.extend(self._experience_to_documents(exp))

        if not all_documents:
            return 0

        await self.store.add_experiences(user_id, all_documents)
        return len(all_documents)

    async def embed_single_experience(
        self, user_id: str, experience: Experience
    ) -> int:
        """
        Embed a single experience (useful when user adds a new role).
        Returns the number of documents embedded.
        """
        documents = self._experience_to_documents(experience)
        if not documents:
            return 0

        await self.store.add_experiences(user_id, documents)
        return len(documents)
