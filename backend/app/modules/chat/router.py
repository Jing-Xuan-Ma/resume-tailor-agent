"""
Chat API Routes — Handles conversational interactions with the agent.
"""

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.modules.chat.schemas import ChatRequest, ChatResponse
from app.modules.chat.service import ChatService

router = APIRouter()
chat_service = ChatService()


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a message to the agent and get a response.
    """
    response = await chat_service.handle_message(
        user_id=request.user_id,
        session_id=request.session_id,
        message=request.message,
        context=request.context,
    )
    return response


@router.websocket("/ws/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time chat.
    """
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")
            session_id = data.get("session_id")

            # Stream agent response
            async for chunk in chat_service.stream_message(
                user_id=UUID(user_id),
                session_id=UUID(session_id) if session_id else None,
                message=message,
            ):
                await websocket.send_json({"type": "stream", "content": chunk})

            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "content": str(e)})
