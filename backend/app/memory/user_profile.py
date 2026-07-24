"""
User preference profile manager.
Learns and evolves user preferences from feedback.
"""

from typing import Optional
from uuid import UUID

from app.core.models import UserPreferenceProfile
from app import db


class UserProfileManager:
    """
    Manages dynamic user preference profiles.
    """

    def __init__(self, long_term_store):
        self.long_term = long_term_store

    async def get_profile(self, user_id: str) -> UserPreferenceProfile:
        """
        Retrieve user preference profile.
        """
        stored = db.get_profile(user_id)
        if stored:
            return UserPreferenceProfile(**stored)
        profile = UserPreferenceProfile()
        db.save_profile(user_id, profile.model_dump())
        return profile

    async def update_from_feedback(self, user_id: str, feedback: dict):
        """
        Evolve preferences based on user feedback.
        e.g., user consistently rewrites bullets to be shorter -> decrease verbosity.
        """
        profile = await self.get_profile(user_id)
        text = " ".join(str(v).lower() for v in feedback.values())
        if any(term in text for term in ["shorter", "concise", "brief", "精简", "缩短"]):
            profile.verbosity = "concise"
        if any(term in text for term in ["formal", "正式"]):
            profile.tone = "formal"
        if any(term in text for term in ["casual", "自然"]):
            profile.tone = "casual"
        if any(term in text for term in ["no metrics", "不要数字", "less metrics"]):
            profile.metric_emphasis = False
        avoided = feedback.get("avoid") or feedback.get("avoided_phrases")
        if isinstance(avoided, str) and avoided not in profile.avoided_phrases:
            profile.avoided_phrases.append(avoided)
        db.save_profile(user_id, profile.model_dump())
        return profile
