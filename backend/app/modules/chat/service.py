"""
Chat Service — Orchestrates conversation flow and delegates to resume tailor when needed.
"""

from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

from langchain_openai import ChatOpenAI

from app import db
from app.config import settings
from app.core.events import ConversationTurnEvent, event_bus
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
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            kwargs = {
                "model": settings.DEFAULT_PARSER_MODEL,
                "temperature": 0.4,
                "api_key": settings.OPENAI_API_KEY,
                "max_tokens": 1000,
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            self._llm = ChatOpenAI(**kwargs)
        return self._llm

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
        db.save_conversation_turn(str(user_id), str(session_id), "user", message)
        try:
            await self.long_term.add_conversation_turn(str(user_id), str(session_id), message, "user")
            await event_bus.publish(
                ConversationTurnEvent(session_id=session_id, user_id=user_id, role="user", content=message)
            )
        except Exception:
            pass

        message_lower = message.lower()
        looks_like_jd = len(message) > 200 and any(
            marker in message_lower
            for marker in [
                "responsibilities",
                "requirements",
                "qualifications",
                "experience",
                "skills",
                "job description",
            ]
        )

        if looks_like_jd:
            agent_message = "⏳ Tailoring your resume now..."
            agent_state = "tailoring"
            suggested_actions = ["Review tailored resume", "Export PDF", "Export Word"]
        else:
            agent_message = await self._answer_general_chat(str(session_id), message, context or {})
            agent_state = "chatting"
            suggested_actions = ["Upload resume", "Paste JD", "Ask for resume edits"]

        # Store assistant message
        self.conversation.add_message(
            str(session_id),
            ChatMessage(role="assistant", content=agent_message),
        )
        db.save_conversation_turn(str(user_id), str(session_id), "assistant", agent_message)
        try:
            await self.long_term.add_conversation_turn(str(user_id), str(session_id), agent_message, "assistant")
            await event_bus.publish(
                ConversationTurnEvent(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant",
                    content=agent_message,
                    agent_state=agent_state,
                )
            )
        except Exception:
            pass

        return ChatResponse(
            session_id=session_id,
            agent_message=agent_message,
            agent_state=agent_state,
            suggested_actions=suggested_actions,
        )

    async def _answer_general_chat(self, session_id: str, message: str, context: dict) -> str:
        recent = self.conversation.get_recent_messages(session_id, limit=8)
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in recent
            if msg.role in {"user", "assistant"}
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ResumeAgent, a concise AI resume tailoring assistant. "
                    "Answer normal user questions naturally. If the user asks about resumes, JD tailoring, "
                    "exports, formatting, or editing, give practical guidance. Do not claim you have tailored "
                    "a resume unless a JD and resume draft are available. Keep answers brief and helpful."
                ),
            },
            *history,
        ]
        if context:
            messages.insert(
                1,
                {
                    "role": "system",
                    "content": f"Current UI/session context: {context}",
                },
            )
        try:
            response = await self._get_llm().ainvoke(messages)
            content = str(response.content).strip()
            if content:
                return content
        except Exception as exc:
            return (
                "I can help with resume tailoring, JD matching, formatting, and exports. "
                f"The general chat model is currently unavailable: {exc}"
            )
        return "I can help with resume tailoring, JD matching, formatting, and exports."

    async def stream_message(
        self,
        user_id: UUID,
        session_id: Optional[UUID],
        message: str,
    ) -> AsyncGenerator[str, None]:
        """
        Return chat output through the WebSocket endpoint.

        The current LLM provider path is non-streaming, so this yields the final
        response as one chunk while keeping the WebSocket contract usable.
        """
        response = await self.handle_message(
            user_id=user_id,
            session_id=session_id,
            message=message,
        )
        yield response.agent_message
