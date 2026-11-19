"""FastAPI application entry point for FinAlly."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import Database
from app.market import (
    MarketDataSource,
    PriceCache,
    create_market_data_source,
    create_stream_router,
)
from app.routes import (
    create_chat_router,
    create_portfolio_router,
    create_watchlist_router,
)
from app.schemas import HealthResponse
from app.services import (
    ChatService,
    FixedWindowRateLimiter,
    PortfolioService,
    WatchlistService,
)

# Load .env from repo root (or current directory) if present
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

logger = logging.getLogger(__name__)


async def _snapshot_loop(portfolio_service: PortfolioService, interval: float) -> None:
    """Periodically record a portfolio value snapshot for the P&L chart."""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                portfolio_service.record_snapshot()
            except Exception as exc:
                logger.error("Failed to record portfolio snapshot: %s", exc, exc_info=True)
    except asyncio.CancelledError:
        logger.debug("Portfolio snapshot task cancelled")
        raise


def _resolve_static_dir(explicit_dir: str | Path | None = None) -> Path | None:
    if explicit_dir is not None:
        candidate = Path(explicit_dir)
        return candidate if candidate.is_dir() else None

    package_root = Path(__file__).resolve().parents[1]
    for candidate in (package_root / "static", _REPO_ROOT / "frontend" / "out"):
        if candidate.is_dir():
            return candidate
    return None


def create_app(
    *,
    db_path: str | Path | None = None,
    price_cache: PriceCache | None = None,
    market_data_source: MarketDataSource | None = None,
    snapshot_interval: float = 30.0,
    static_dir: str | Path | None = None,
    chat_rate_limit: int = 10,
) -> FastAPI:
    """Create and configure a FinAlly FastAPI application instance."""
    cache = price_cache if price_cache is not None else PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(db_path=db_path)
        db.init()

        source = (
            market_data_source
            if market_data_source is not None
            else create_market_data_source(cache)
        )
        tracked_tickers = db.get_tracked_tickers()
        await source.start(tracked_tickers)

        portfolio_service = PortfolioService(
            db=db,
            price_cache=cache,
            market_data_source=source,
        )
        watchlist_service = WatchlistService(
            db=db,
            price_cache=cache,
            market_data_source=source,
        )
        chat_service = ChatService(
            db=db,
            portfolio_service=portfolio_service,
            watchlist_service=watchlist_service,
        )

        app.state.db = db
        app.state.price_cache = cache
        app.state.market_data_source = source
        app.state.portfolio_service = portfolio_service
        app.state.watchlist_service = watchlist_service
        app.state.chat_service = chat_service
        app.state.chat_rate_limiter = FixedWindowRateLimiter(
            max_requests=chat_rate_limit,
            window_seconds=60.0,
        )

        snapshot_task = asyncio.create_task(_snapshot_loop(portfolio_service, snapshot_interval))
        logger.info(
            "FinAlly started (db=%s, source=%s, tracked=%d)",
            db.db_path,
            type(source).__name__,
            len(tracked_tickers),
        )

        try:
            yield
        finally:
            snapshot_task.cancel()
            try:
                await snapshot_task
            except asyncio.CancelledError:
                pass
            await source.stop()
            logger.info("FinAlly shut down cleanly")

    app = FastAPI(
        title="FinAlly API",
        version="0.1.0",
        description="AI Trading Workstation backend API",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def app_password_middleware(request: Request, call_next):
        expected = os.environ.get("APP_PASSWORD", "").strip()
        path = request.url.path
        if expected and path.startswith("/api/") and path != "/api/health":
            provided = request.headers.get("X-App-Password")
            if provided is None and path == "/api/stream/prices":
                provided = request.query_params.get("key")
            if not provided or not hmac.compare_digest(provided, expected):
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    async def health(request: Request) -> HealthResponse:
        source: MarketDataSource = request.app.state.market_data_source
        return HealthResponse(
            status="ok",
            market_data_source=type(source).__name__,
            tracked_tickers=len(source.get_tickers()),
        )

    app.include_router(create_stream_router(cache))
    app.include_router(create_portfolio_router())
    app.include_router(create_watchlist_router())
    app.include_router(create_chat_router())

    resolved_static = _resolve_static_dir(static_dir)
    if resolved_static is not None:
        app.mount("/", StaticFiles(directory=resolved_static, html=True), name="static")

    return app


app = create_app()
