"""
Chat Service — Orchestrates conversation flow and delegates to resume tailor when needed.
"""

from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

from app.memory.conversation import ConversationMemoryManager
from app.memory.long_term import LongTermMemoryStore
from app.core.models import ChatMessage
from app.modules.chat.schemas import ChatResponse


class ChatService:
    """
    Handles chat logic: intent routing, session management, and integration
    with the resume tailor agent.
    """

    def __init__(self):
        self.long_term = LongTermMemoryStore()
        self.conversation = ConversationMemoryManager(self.long_term)

    async def handle_message(
        self,
        user_id: UUID,
        session_id: Optional[UUID],
        message: str,
        context: Optional[dict] = None,
    ) -> ChatResponse:
        """
        Process a user message and return agent response.
        """
        if not session_id:
            session_id = uuid4()

        # Store user message
        self.conversation.add_message(
            str(session_id),
            ChatMessage(role="user", content=message),
        )

        # TODO: Intent classification
        # If message contains JD -> trigger resume tailor
        # If general question -> direct LLM response

        agent_message = (
            "I've received your message. To tailor your resume, please paste the job description "
            "you're targeting, or upload a link to the posting."
        )

        # Store assistant message
        self.conversation.add_message(
            str(session_id),
            ChatMessage(role="assistant", content=agent_message),
        )

        return ChatResponse(
            session_id=session_id,
            agent_message=agent_message,
            agent_state="idle",
            suggested_actions=["Paste JD", "Upload resume", "View history"],
        )

    async def stream_message(
        self,
        user_id: UUID,
        session_id: Optional[UUID],
        message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Stream agent response token-by-token.
        TODO: Integrate with LLM streaming.
        """
        yield "Processing..."
        # Placeholder for streaming implementation
