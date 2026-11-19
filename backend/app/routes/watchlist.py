"""Watchlist REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas import (
    Ticker,
    WatchlistAddRequest,
    WatchlistItemResponse,
    WatchlistRemoveResponse,
    WatchlistResponse,
)
from app.services import ConflictError, NotFoundError, WatchlistService


def create_watchlist_router() -> APIRouter:
    router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

    @router.get("", response_model=WatchlistResponse)
    async def get_watchlist(request: Request) -> WatchlistResponse:
        service: WatchlistService = request.app.state.watchlist_service
        return service.get_watchlist()

    @router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
    async def add_to_watchlist(
        body: WatchlistAddRequest, request: Request
    ) -> WatchlistItemResponse:
        service: WatchlistService = request.app.state.watchlist_service
        try:
            return await service.add_ticker(body.ticker)
        except ConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.delete("/{ticker}", response_model=WatchlistRemoveResponse)
    async def remove_from_watchlist(
        ticker: Ticker, request: Request
    ) -> WatchlistRemoveResponse:
        service: WatchlistService = request.app.state.watchlist_service
        try:
            return await service.remove_ticker(ticker)
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return router
