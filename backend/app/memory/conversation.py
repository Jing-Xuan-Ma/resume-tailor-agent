"""
Conversation memory manager.
Handles short-term buffer and long-term archival with automatic summarization.
"""

from typing import List, Optional
from uuid import UUID

from app.core.models import ChatMessage
from app import db


class ConversationMemoryManager:
    """
    Manages conversation history with:
    - Working memory (last 5 turns)
    - Short-term memory (last 20 turns)
    - Long-term memory (vector store + compressed summaries)
    """

    def __init__(self, long_term_store):
        self.long_term = long_term_store
        self._buffers: dict[str, List[ChatMessage]] = {}  # In-memory session buffers

    def add_message(self, session_id: str, message: ChatMessage):
        """Add a message to the session buffer."""
        if session_id not in self._buffers:
            self._buffers[session_id] = []
        self._buffers[session_id].append(message)

    def get_recent_messages(self, session_id: str, limit: int = 10) -> List[ChatMessage]:
        """Get recent messages from working memory."""
        buffer = self._buffers.get(session_id, [])
        return buffer[-limit:]

    async def archive_session(self, session_id: str, user_id: str):
        """
        Archive session messages to long-term memory and clear buffer.
        Called when session ends or periodically.
        """
        buffer = self._buffers.get(session_id, [])
        if not buffer:
            return

        for msg in buffer:
            db.save_conversation_turn(str(user_id), session_id, msg.role, msg.content)
            await self.long_term.add_conversation_turn(
                user_id=str(user_id),
                session_id=session_id,
                text=msg.content,
                role=msg.role,
            )

        # Clear buffer
        self._buffers[session_id] = []

    async def compress_if_needed(self, session_id: str, llm_client):
        """
        If conversation exceeds threshold, generate summary and archive.
        Compress long sessions into a durable summary entry.
        """
        buffer = self._buffers.get(session_id, [])
        if len(buffer) >= 50:
            text = "\n".join(f"{msg.role}: {msg.content}" for msg in buffer[-50:])
            try:
                response = await llm_client.ainvoke([
                    {"role": "system", "content": "Summarize this resume assistant conversation into durable user preferences and facts."},
                    {"role": "user", "content": text},
                ])
                summary = str(response.content).strip()
            except Exception:
                summary = text[:2000]
            await self.long_term.add_conversation_turn("unknown", session_id, summary, "system")
