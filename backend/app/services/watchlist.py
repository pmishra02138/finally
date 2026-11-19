"""Watchlist management service coordinating SQLite and MarketDataSource."""

from __future__ import annotations

from app.db import DEFAULT_USER_ID, Database
from app.market import MarketDataSource, PriceCache
from app.schemas import WatchlistItemResponse, WatchlistRemoveResponse, WatchlistResponse


class ConflictError(Exception):
    """Resource conflict (maps to HTTP 409 Conflict)."""


class NotFoundError(Exception):
    """Resource not found (maps to HTTP 404 Not Found)."""


class WatchlistService:
    """Manages watched tickers and keeps MarketDataSource synchronized."""

    def __init__(
        self,
        db: Database,
        price_cache: PriceCache,
        market_data_source: MarketDataSource,
    ) -> None:
        self.db = db
        self.price_cache = price_cache
        self.market_data_source = market_data_source

    def _build_item(self, ticker: str, added_at: str) -> WatchlistItemResponse:
        update = self.price_cache.get(ticker)
        if update is None:
            return WatchlistItemResponse(ticker=ticker, added_at=added_at)
        return WatchlistItemResponse(
            ticker=ticker,
            price=update.price,
            previous_price=update.previous_price,
            change=update.change,
            change_percent=update.change_percent,
            direction=update.direction,
            timestamp=update.timestamp,
            added_at=added_at,
        )

    def get_watchlist(self, user_id: str = DEFAULT_USER_ID) -> WatchlistResponse:
        rows = self.db.get_watchlist(user_id=user_id)
        items = [self._build_item(row["ticker"], row["added_at"]) for row in rows]
        return WatchlistResponse(tickers=items)

    async def add_ticker(
        self, ticker: str, user_id: str = DEFAULT_USER_ID
    ) -> WatchlistItemResponse:
        row = self.db.add_to_watchlist(ticker, user_id=user_id)
        if row is None:
            raise ConflictError(f"Ticker {ticker} is already in watchlist")
        await self.market_data_source.add_ticker(ticker)
        return self._build_item(ticker, row["added_at"])

    async def remove_ticker(
        self, ticker: str, user_id: str = DEFAULT_USER_ID
    ) -> WatchlistRemoveResponse:
        removed = self.db.remove_from_watchlist(ticker, user_id=user_id)
        if not removed:
            raise NotFoundError(f"Ticker {ticker} not found in watchlist")
        if not self.db.has_position(ticker, user_id=user_id):
            await self.market_data_source.remove_ticker(ticker)
        return WatchlistRemoveResponse(ticker=ticker, removed=True)
