"""Portfolio REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.schemas import (
    PortfolioResponse,
    PortfolioSnapshotResponse,
    TradeRequest,
    TradeResponse,
)
from app.services import DomainError, PortfolioService


def create_portfolio_router() -> APIRouter:
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

    @router.get("", response_model=PortfolioResponse)
    async def get_portfolio(request: Request) -> PortfolioResponse:
        service: PortfolioService = request.app.state.portfolio_service
        return service.get_portfolio()

    @router.post("/trade", response_model=TradeResponse)
    async def execute_trade(body: TradeRequest, request: Request) -> TradeResponse:
        service: PortfolioService = request.app.state.portfolio_service
        try:
            return await service.execute_trade(
                ticker=body.ticker,
                side=body.side,
                quantity=body.quantity,
            )
        except DomainError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/history", response_model=list[PortfolioSnapshotResponse])
    async def get_portfolio_history(request: Request) -> list[PortfolioSnapshotResponse]:
        service: PortfolioService = request.app.state.portfolio_service
        return service.get_history(limit=500)

    return router
