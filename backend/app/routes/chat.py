"""LLM chat REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import ChatHistoryResponse, ChatMessageResponse, ChatRequest
from app.services import ChatService, FixedWindowRateLimiter


def create_chat_router() -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.get("/history", response_model=ChatHistoryResponse)
    async def get_chat_history(request: Request) -> ChatHistoryResponse:
        service: ChatService = request.app.state.chat_service
        return service.get_history(limit=50)

    @router.post("", response_model=ChatMessageResponse)
    async def post_chat(body: ChatRequest, request: Request) -> ChatMessageResponse:
        limiter: FixedWindowRateLimiter = request.app.state.chat_rate_limiter
        if not limiter.allow():
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Maximum 10 requests per minute.",
            )
        service: ChatService = request.app.state.chat_service
        return await service.process_message(body.message)

    return router
