"""Portfolio valuation, trade execution, and snapshot services."""

from __future__ import annotations

import uuid

from app.db import DEFAULT_USER_ID, Database, utc_now_iso
from app.market import MarketDataSource, PriceCache
from app.schemas import (
    PortfolioResponse,
    PortfolioSnapshotResponse,
    PositionResponse,
    TradeRecord,
    TradeResponse,
)

QTY_EPSILON = 1e-9


class DomainError(Exception):
    """Domain validation error (maps to HTTP 400 Bad Request)."""


class PortfolioService:
    """Handles portfolio valuation, atomic trade execution, and history snapshots."""

    def __init__(
        self,
        db: Database,
        price_cache: PriceCache,
        market_data_source: MarketDataSource,
    ) -> None:
        self.db = db
        self.price_cache = price_cache
        self.market_data_source = market_data_source

    def _compute_portfolio(
        self,
        cash_balance: float,
        position_rows: list[dict],
    ) -> PortfolioResponse:
        preliminary: list[dict] = []
        total_positions_value = 0.0
        total_cost_basis = 0.0
        total_unrealized_pnl = 0.0

        for row in position_rows:
            ticker = row["ticker"]
            quantity = float(row["quantity"])
            avg_cost = float(row["avg_cost"])
            cached_price = self.price_cache.get_price(ticker)
            current_price = cached_price if cached_price is not None else avg_cost

            market_value = quantity * current_price
            cost_basis = quantity * avg_cost
            unrealized_pnl = market_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

            total_positions_value += market_value
            total_cost_basis += cost_basis
            total_unrealized_pnl += unrealized_pnl

            preliminary.append(
                {
                    "ticker": ticker,
                    "quantity": quantity,
                    "avg_cost": avg_cost,
                    "current_price": current_price,
                    "market_value": market_value,
                    "unrealized_pnl": unrealized_pnl,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                }
            )

        total_value = cash_balance + total_positions_value
        total_unrealized_pnl_pct = (
            (total_unrealized_pnl / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0
        )

        positions = [
            PositionResponse(
                ticker=p["ticker"],
                quantity=round(p["quantity"], 6),
                avg_cost=round(p["avg_cost"], 4),
                current_price=round(p["current_price"], 2),
                market_value=round(p["market_value"], 2),
                unrealized_pnl=round(p["unrealized_pnl"], 2),
                unrealized_pnl_pct=round(p["unrealized_pnl_pct"], 2),
                weight_pct=round((p["market_value"] / total_value * 100.0) if total_value > 0 else 0.0, 2),
            )
            for p in preliminary
        ]

        return PortfolioResponse(
            cash_balance=round(cash_balance, 2),
            total_value=round(total_value, 2),
            total_unrealized_pnl=round(total_unrealized_pnl, 2),
            total_unrealized_pnl_pct=round(total_unrealized_pnl_pct, 2),
            positions=positions,
        )

    def get_portfolio(self, user_id: str = DEFAULT_USER_ID) -> PortfolioResponse:
        cash_balance = self.db.get_cash_balance(user_id)
        position_rows = self.db.get_positions(user_id)
        return self._compute_portfolio(cash_balance, position_rows)

    def record_snapshot(self, user_id: str = DEFAULT_USER_ID) -> PortfolioSnapshotResponse:
        portfolio = self.get_portfolio(user_id)
        row = self.db.record_portfolio_snapshot(portfolio.total_value, user_id=user_id)
        return PortfolioSnapshotResponse(
            total_value=row["total_value"],
            recorded_at=row["recorded_at"],
        )

    def get_history(
        self, limit: int = 500, user_id: str = DEFAULT_USER_ID
    ) -> list[PortfolioSnapshotResponse]:
        rows = self.db.get_portfolio_history(limit=limit, user_id=user_id)
        return [
            PortfolioSnapshotResponse(
                total_value=float(r["total_value"]),
                recorded_at=r["recorded_at"],
            )
            for r in rows
        ]

    async def execute_trade(
        self,
        ticker: str,
        side: str,
        quantity: float,
        user_id: str = DEFAULT_USER_ID,
    ) -> TradeResponse:
        """Execute a market buy or sell order atomically."""
        if side == "buy":
            if not self.db.is_in_watchlist(ticker, user_id=user_id):
                self.db.add_to_watchlist(ticker, user_id=user_id)
                await self.market_data_source.add_ticker(ticker)

        price = self.price_cache.get_price(ticker)
        if price is None:
            raise DomainError(f"Price not yet available for {ticker}")

        now = utc_now_iso()
        trade_id = str(uuid.uuid4())
        position_closed = False

        with self.db.connection() as conn:
            profile_row = conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?",
                (user_id,),
            ).fetchone()
            if profile_row is None:
                raise RuntimeError(f"User profile '{user_id}' not initialized")
            cash_balance = float(profile_row["cash_balance"])

            pos_row = conn.execute(
                "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()

            if side == "buy":
                cost = quantity * price
                if cash_balance < cost - QTY_EPSILON:
                    raise DomainError(
                        f"Insufficient cash: need ${cost:,.2f}, have ${cash_balance:,.2f}"
                    )
                new_cash = max(0.0, cash_balance - cost)

                if pos_row is None:
                    conn.execute(
                        """
                        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), user_id, ticker, quantity, price, now),
                    )
                else:
                    old_qty = float(pos_row["quantity"])
                    old_avg = float(pos_row["avg_cost"])
                    new_qty = old_qty + quantity
                    new_avg = (old_qty * old_avg + quantity * price) / new_qty
                    conn.execute(
                        """
                        UPDATE positions
                        SET quantity = ?, avg_cost = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (new_qty, new_avg, now, pos_row["id"]),
                    )

            elif side == "sell":
                if pos_row is None:
                    raise DomainError(f"No open position in {ticker} to sell")
                held_qty = float(pos_row["quantity"])
                if held_qty < quantity - QTY_EPSILON:
                    raise DomainError(
                        f"Insufficient shares of {ticker}: requested {quantity}, held {held_qty}"
                    )
                proceeds = quantity * price
                new_cash = cash_balance + proceeds
                remaining = held_qty - quantity

                if remaining <= QTY_EPSILON:
                    conn.execute("DELETE FROM positions WHERE id = ?", (pos_row["id"],))
                    position_closed = True
                else:
                    conn.execute(
                        "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
                        (remaining, now, pos_row["id"]),
                    )
            else:
                raise DomainError(f"Invalid trade side: {side}")

            conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                (new_cash, user_id),
            )
            conn.execute(
                """
                INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trade_id, user_id, ticker, side, quantity, price, now),
            )

            updated_positions = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, ticker, quantity, avg_cost, updated_at
                    FROM positions
                    WHERE user_id = ?
                    ORDER BY ticker ASC
                    """,
                    (user_id,),
                ).fetchall()
            ]
            portfolio = self._compute_portfolio(new_cash, updated_positions)

            conn.execute(
                """
                INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user_id, portfolio.total_value, now),
            )

        if position_closed and not self.db.is_in_watchlist(ticker, user_id=user_id):
            await self.market_data_source.remove_ticker(ticker)

        trade = TradeRecord(
            id=trade_id,
            ticker=ticker,
            side=side,  # type: ignore[arg-type]
            quantity=round(quantity, 6),
            price=round(price, 2),
            executed_at=now,
        )
        return TradeResponse(trade=trade, portfolio=portfolio)
