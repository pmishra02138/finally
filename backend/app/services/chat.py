"""LLM chat service with Gemini (Google AI Studio) structured outputs, mock mode, and auto-execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

from pydantic import ValidationError

from app.db import DEFAULT_USER_ID, Database
from app.schemas import (
    ChatActionResult,
    ChatHistoryResponse,
    ChatMessageResponse,
    LLMResponse,
    Trade,
    TradeRequest,
    WatchlistAddRequest,
    WatchlistChange,
)
from app.services.portfolio import DomainError, PortfolioService
from app.services.watchlist import ConflictError, NotFoundError, WatchlistService

# Avoid blocking network cost-map fetch on import when offline
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import litellm  # noqa: E402

logger = logging.getLogger(__name__)

MODEL = "gemini/gemini-3.1-flash-lite"
LLM_TIMEOUT_SECONDS = 30.0
FALLBACK_MESSAGE = "Sorry, I couldn't process that request. Please try again."

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant integrated into a simulated trading workstation.

Responsibilities:
- Analyze the user's portfolio composition, risk concentration, cash balance, and unrealized P&L.
- Suggest trades with clear, concise, data-driven reasoning.
- Execute trades automatically when the user asks or agrees.
- Manage the user's watchlist proactively when requested or helpful.
- Be concise and data-driven in your responses.

Output requirements:
- Always respond with valid JSON matching the required schema:
  {"message": "...", "trades": [...], "watchlist_changes": [...]}
- Use empty arrays [] for "trades" and "watchlist_changes" when no actions are needed.
- Tickers must be 1 to 5 uppercase letters (e.g. "AAPL"). Quantities must be positive numbers.
- All trades are market orders executed immediately against simulated cash.
"""

_BUY_PATTERN = re.compile(r"\bbuy\s+([0-9]+(?:\.[0-9]+)?)\s+([a-zA-Z]{1,10})\b", re.IGNORECASE)
_SELL_PATTERN = re.compile(r"\bsell\s+([0-9]+(?:\.[0-9]+)?)\s+([a-zA-Z]{1,10})\b", re.IGNORECASE)
_WATCH_PATTERN = re.compile(r"\b(?:watch|add)\s+([a-zA-Z]{1,10})\b", re.IGNORECASE)
_UNWATCH_PATTERN = re.compile(r"\b(?:unwatch|remove)\s+([a-zA-Z]{1,10})\b", re.IGNORECASE)


class FixedWindowRateLimiter:
    """In-memory fixed-window rate limiter (default: 10 requests per 60 seconds)."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._window_start = 0.0
        self._count = 0

    def allow(self) -> bool:
        now = time.monotonic()
        if now - self._window_start >= self.window_seconds:
            self._window_start = now
            self._count = 0
        if self._count >= self.max_requests:
            return False
        self._count += 1
        return True


def _is_mock_mode() -> bool:
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


class ChatService:
    """Handles chat history, LLM calls (real or mock), and action auto-execution."""

    def __init__(
        self,
        db: Database,
        portfolio_service: PortfolioService,
        watchlist_service: WatchlistService,
    ) -> None:
        self.db = db
        self.portfolio_service = portfolio_service
        self.watchlist_service = watchlist_service

    def get_history(
        self, limit: int = 50, user_id: str = DEFAULT_USER_ID
    ) -> ChatHistoryResponse:
        rows = self.db.get_chat_messages(limit=limit, user_id=user_id)
        messages: list[ChatMessageResponse] = []
        for row in rows:
            actions: list[ChatActionResult] | None = None
            if row["actions"] is not None:
                raw_actions = json.loads(row["actions"])
                actions = [ChatActionResult.model_validate(a) for a in raw_actions]
            messages.append(
                ChatMessageResponse(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    actions=actions,
                    created_at=row["created_at"],
                )
            )
        return ChatHistoryResponse(messages=messages)

    def _build_portfolio_context(self, user_id: str = DEFAULT_USER_ID) -> str:
        portfolio = self.portfolio_service.get_portfolio(user_id=user_id)
        watchlist = self.watchlist_service.get_watchlist(user_id=user_id)

        lines = [
            "Current Portfolio Context:",
            f"- Cash Balance: ${portfolio.cash_balance:,.2f}",
            f"- Total Portfolio Value: ${portfolio.total_value:,.2f}",
            f"- Total Unrealized P&L: ${portfolio.total_unrealized_pnl:+,.2f} ({portfolio.total_unrealized_pnl_pct:+.2f}%)",
        ]

        if portfolio.positions:
            lines.append("- Open Positions:")
            for pos in portfolio.positions:
                lines.append(
                    f"  * {pos.ticker}: {pos.quantity} shares @ avg ${pos.avg_cost:,.2f} "
                    f"(current ${pos.current_price:,.2f}, value ${pos.market_value:,.2f}, "
                    f"P&L ${pos.unrealized_pnl:+,.2f} / {pos.unrealized_pnl_pct:+.2f}%, "
                    f"weight {pos.weight_pct:.2f}%)"
                )
        else:
            lines.append("- Open Positions: None")

        if watchlist.tickers:
            watched_strs = [
                f"{w.ticker} (${w.price:,.2f})" if w.price is not None else f"{w.ticker} (pending)"
                for w in watchlist.tickers
            ]
            lines.append(f"- Watchlist: {', '.join(watched_strs)}")
        else:
            lines.append("- Watchlist: Empty")

        return "\n".join(lines)

    def _mock_response(self, user_message: str, user_id: str = DEFAULT_USER_ID) -> LLMResponse:
        buy_match = _BUY_PATTERN.search(user_message)
        if buy_match:
            qty = float(buy_match.group(1))
            ticker = buy_match.group(2).upper()
            return LLMResponse(
                message=f"Buying {qty:g} shares of {ticker}.",
                trades=[Trade(ticker=ticker, side="buy", quantity=qty)],
                watchlist_changes=[],
            )

        sell_match = _SELL_PATTERN.search(user_message)
        if sell_match:
            qty = float(sell_match.group(1))
            ticker = sell_match.group(2).upper()
            return LLMResponse(
                message=f"Selling {qty:g} shares of {ticker}.",
                trades=[Trade(ticker=ticker, side="sell", quantity=qty)],
                watchlist_changes=[],
            )

        unwatch_match = _UNWATCH_PATTERN.search(user_message)
        if unwatch_match:
            ticker = unwatch_match.group(1).upper()
            return LLMResponse(
                message=f"Removing {ticker} from your watchlist.",
                trades=[],
                watchlist_changes=[WatchlistChange(ticker=ticker, action="remove")],
            )

        watch_match = _WATCH_PATTERN.search(user_message)
        if watch_match:
            ticker = watch_match.group(1).upper()
            return LLMResponse(
                message=f"Adding {ticker} to your watchlist.",
                trades=[],
                watchlist_changes=[WatchlistChange(ticker=ticker, action="add")],
            )

        portfolio = self.portfolio_service.get_portfolio(user_id=user_id)
        return LLMResponse(
            message=(
                f"Your portfolio currently has ${portfolio.cash_balance:,.2f} in cash, "
                f"{len(portfolio.positions)} open position(s), and a total value of "
                f"${portfolio.total_value:,.2f}."
            ),
            trades=[],
            watchlist_changes=[],
        )

    async def _call_llm_once(self, messages: list[dict[str, str]]) -> LLMResponse:
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "messages": messages,
            "response_format": LLMResponse,
            "reasoning_effort": "low",
        }
        if gemini_key:
            kwargs["api_key"] = gemini_key

        response = await asyncio.wait_for(
            litellm.acompletion(**kwargs),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("LLM returned empty content")
        return LLMResponse.model_validate_json(content)

    async def _get_llm_response(
        self,
        user_message: str,
        history_rows: list[dict],
        portfolio_context: str,
        user_id: str = DEFAULT_USER_ID,
    ) -> LLMResponse:
        if _is_mock_mode():
            return self._mock_response(user_message, user_id=user_id)

        messages: list[dict[str, str]] = [
            {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{portfolio_context}"}
        ]
        for row in history_rows:
            messages.append({"role": row["role"], "content": row["content"]})
        messages.append({"role": "user", "content": user_message})

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                return await self._call_llm_once(messages)
            except Exception as exc:
                last_exc = exc
                logger.warning("LLM call attempt %d failed: %s", attempt + 1, exc)

        logger.error("LLM call failed after retry: %s", last_exc)
        return LLMResponse(message=FALLBACK_MESSAGE, trades=[], watchlist_changes=[])

    async def _execute_actions(
        self, llm_response: LLMResponse, user_id: str = DEFAULT_USER_ID
    ) -> list[ChatActionResult]:
        results: list[ChatActionResult] = []

        for trade in llm_response.trades:
            try:
                validated = TradeRequest(
                    ticker=trade.ticker,
                    side=trade.side,
                    quantity=trade.quantity,
                )
            except ValidationError as exc:
                err_msg = "; ".join(e["msg"] for e in exc.errors())
                results.append(
                    ChatActionResult(
                        type="trade",
                        ticker=trade.ticker.strip().upper(),
                        side=trade.side,
                        quantity=trade.quantity,
                        price=None,
                        action=None,
                        status="failed",
                        error=err_msg,
                    )
                )
                continue

            try:
                trade_resp = await self.portfolio_service.execute_trade(
                    ticker=validated.ticker,
                    side=validated.side,
                    quantity=validated.quantity,
                    user_id=user_id,
                )
                results.append(
                    ChatActionResult(
                        type="trade",
                        ticker=validated.ticker,
                        side=validated.side,
                        quantity=validated.quantity,
                        price=trade_resp.trade.price,
                        action=None,
                        status="executed",
                        error=None,
                    )
                )
            except DomainError as exc:
                results.append(
                    ChatActionResult(
                        type="trade",
                        ticker=validated.ticker,
                        side=validated.side,
                        quantity=validated.quantity,
                        price=None,
                        action=None,
                        status="failed",
                        error=str(exc),
                    )
                )

        for change in llm_response.watchlist_changes:
            try:
                validated_wl = WatchlistAddRequest(ticker=change.ticker)
            except ValidationError as exc:
                err_msg = "; ".join(e["msg"] for e in exc.errors())
                results.append(
                    ChatActionResult(
                        type="watchlist",
                        ticker=change.ticker.strip().upper(),
                        side=None,
                        quantity=None,
                        price=None,
                        action=change.action,
                        status="failed",
                        error=err_msg,
                    )
                )
                continue

            try:
                if change.action == "add":
                    await self.watchlist_service.add_ticker(validated_wl.ticker, user_id=user_id)
                else:
                    await self.watchlist_service.remove_ticker(validated_wl.ticker, user_id=user_id)
                results.append(
                    ChatActionResult(
                        type="watchlist",
                        ticker=validated_wl.ticker,
                        side=None,
                        quantity=None,
                        price=None,
                        action=change.action,
                        status="executed",
                        error=None,
                    )
                )
            except (ConflictError, NotFoundError) as exc:
                results.append(
                    ChatActionResult(
                        type="watchlist",
                        ticker=validated_wl.ticker,
                        side=None,
                        quantity=None,
                        price=None,
                        action=change.action,
                        status="failed",
                        error=str(exc),
                    )
                )

        return results

    async def process_message(
        self, user_message: str, user_id: str = DEFAULT_USER_ID
    ) -> ChatMessageResponse:
        """Process a user chat message end-to-end."""
        portfolio_context = self._build_portfolio_context(user_id=user_id)
        history_rows = self.db.get_chat_messages(limit=20, user_id=user_id)

        # Persist incoming user message
        self.db.add_chat_message(
            role="user",
            content=user_message,
            actions_json=None,
            user_id=user_id,
        )

        # Single LLM call (with 1 retry on failure, fallback to HTTP 200)
        llm_response = await self._get_llm_response(
            user_message=user_message,
            history_rows=history_rows,
            portfolio_context=portfolio_context,
            user_id=user_id,
        )

        # Auto-execute trades & watchlist changes
        actions = await self._execute_actions(llm_response, user_id=user_id)
        actions_json = json.dumps([a.model_dump() for a in actions])

        # Persist assistant message
        saved = self.db.add_chat_message(
            role="assistant",
            content=llm_response.message,
            actions_json=actions_json,
            user_id=user_id,
        )

        return ChatMessageResponse(
            id=saved["id"],
            role="assistant",
            content=saved["content"],
            actions=actions,
            created_at=saved["created_at"],
        )
