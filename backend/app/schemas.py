"""Shared Pydantic schemas and input validators for the FinAlly API."""

from __future__ import annotations

import math
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def _normalize_ticker(value: object) -> object:
    if isinstance(value, str):
        return value.strip().upper()
    return value


def _validate_ticker(value: str) -> str:
    if not TICKER_PATTERN.match(value):
        raise ValueError("Ticker must be 1 to 5 uppercase letters (A-Z)")
    return value


def _validate_positive_finite(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Quantity must be a finite number greater than 0")
    return value


def _strip_non_empty(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value


Ticker = Annotated[
    str,
    BeforeValidator(_normalize_ticker),
    AfterValidator(_validate_ticker),
]

PositiveFiniteFloat = Annotated[
    float,
    AfterValidator(_validate_positive_finite),
]

NonEmptyStr = Annotated[
    str,
    BeforeValidator(_strip_non_empty),
    Field(min_length=1),
]


def normalize_and_validate_ticker(raw: str) -> str:
    """Validate and normalize a raw ticker string, raising ValueError on failure."""
    normalized = raw.strip().upper()
    return _validate_ticker(normalized)


# --- Portfolio Schemas ---


class PositionResponse(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight_pct: float


class PortfolioResponse(BaseModel):
    cash_balance: float
    total_value: float
    total_unrealized_pnl: float
    total_unrealized_pnl_pct: float
    positions: list[PositionResponse]


class TradeRequest(BaseModel):
    ticker: Ticker
    side: Literal["buy", "sell"]
    quantity: PositiveFiniteFloat


class TradeRecord(BaseModel):
    id: str
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    executed_at: str


class TradeResponse(BaseModel):
    trade: TradeRecord
    portfolio: PortfolioResponse


class PortfolioSnapshotResponse(BaseModel):
    total_value: float
    recorded_at: str


# --- Watchlist Schemas ---


class WatchlistItemResponse(BaseModel):
    ticker: str
    price: float | None = None
    previous_price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    direction: Literal["up", "down", "flat"] | None = None
    timestamp: float | None = None
    added_at: str


class WatchlistResponse(BaseModel):
    tickers: list[WatchlistItemResponse]


class WatchlistAddRequest(BaseModel):
    ticker: Ticker


class WatchlistRemoveResponse(BaseModel):
    ticker: str
    removed: bool


# --- Chat & LLM Schemas ---


class ChatRequest(BaseModel):
    message: NonEmptyStr


class ChatActionResult(BaseModel):
    type: Literal["trade", "watchlist"]
    ticker: str
    side: Literal["buy", "sell"] | None = None
    quantity: float | None = None
    price: float | None = None
    action: Literal["add", "remove"] | None = None
    status: Literal["executed", "failed"]
    error: str | None = None


class ChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    actions: list[ChatActionResult] | None = None
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageResponse]


# Strict structured-output models for LLM response_format (all fields required, no defaults)


class Trade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    message: str
    trades: list[Trade]
    watchlist_changes: list[WatchlistChange]


# --- System Schemas ---


class HealthResponse(BaseModel):
    status: Literal["ok"]
    market_data_source: str
    tracked_tickers: int
