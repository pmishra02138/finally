"""Unit and API tests for portfolio valuation, trade execution, and history."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.market import MarketDataSource, PriceCache


class StubMarketDataSource(MarketDataSource):
    """Deterministic in-memory market data source for API tests."""

    def __init__(self, cache: PriceCache, initial_prices: dict[str, float] | None = None) -> None:
        self._cache = cache
        self._initial_prices = initial_prices or {}
        self._tickers: set[str] = set()

    async def start(self, tickers: list[str]) -> None:
        for t in tickers:
            t = t.strip().upper()
            self._tickers.add(t)
            if t in self._initial_prices:
                self._cache.update(t, self._initial_prices[t])

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        t = ticker.strip().upper()
        self._tickers.add(t)
        if t in self._initial_prices:
            self._cache.update(t, self._initial_prices[t])

    async def remove_ticker(self, ticker: str) -> None:
        t = ticker.strip().upper()
        self._tickers.discard(t)
        self._cache.remove(t)

    def get_tickers(self) -> list[str]:
        return sorted(self._tickers)


@pytest.fixture
async def client_and_state(tmp_path: Path):
    cache = PriceCache()
    source = StubMarketDataSource(
        cache,
        initial_prices={"AAPL": 200.0, "GOOGL": 150.0, "MSFT": 400.0, "PYPL": 80.0},
    )
    app = create_app(
        db_path=tmp_path / "test.db",
        price_cache=cache,
        market_data_source=source,
        snapshot_interval=3600.0,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, cache, source


async def test_initial_portfolio(client_and_state) -> None:
    client, _, _ = client_and_state
    resp = await client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cash_balance"] == 10000.0
    assert data["total_value"] == 10000.0
    assert data["total_unrealized_pnl"] == 0.0
    assert data["total_unrealized_pnl_pct"] == 0.0
    assert data["positions"] == []


async def test_buy_weighted_average_and_pnl(client_and_state) -> None:
    client, cache, _ = client_and_state

    # Buy 10 AAPL @ 200
    r1 = await client.post("/api/portfolio/trade", json={"ticker": "aapl", "side": "buy", "quantity": 10})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["trade"]["ticker"] == "AAPL"
    assert body1["trade"]["price"] == 200.0
    assert body1["portfolio"]["cash_balance"] == 8000.0
    assert body1["portfolio"]["positions"][0]["avg_cost"] == 200.0

    # Price rises to 220, buy 10 more AAPL -> avg_cost = 210
    cache.update("AAPL", 220.0)
    r2 = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    assert r2.status_code == 200
    pos = r2.json()["portfolio"]["positions"][0]
    assert pos["quantity"] == 20.0
    assert pos["avg_cost"] == 210.0
    assert pos["current_price"] == 220.0
    assert pos["market_value"] == 4400.0
    assert pos["unrealized_pnl"] == 200.0
    assert pos["unrealized_pnl_pct"] == pytest.approx(4.76, abs=0.01)

    # History has initial + 2 post-trade snapshots
    hist = await client.get("/api/portfolio/history")
    assert hist.status_code == 200
    assert len(hist.json()) == 3


async def test_buy_unwatched_ticker_auto_adds_to_watchlist(client_and_state) -> None:
    client, _, source = client_and_state
    resp = await client.post("/api/portfolio/trade", json={"ticker": "PYPL", "side": "buy", "quantity": 5})
    assert resp.status_code == 200
    assert "PYPL" in source.get_tickers()

    wl = await client.get("/api/watchlist")
    tickers = [item["ticker"] for item in wl.json()["tickers"]]
    assert "PYPL" in tickers


async def test_partial_and_full_sell(client_and_state) -> None:
    client, cache, source = client_and_state

    # Buy 10 AAPL @ 200
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    # Remove AAPL from watchlist while still holding position
    del_resp = await client.delete("/api/watchlist/AAPL")
    assert del_resp.status_code == 200
    assert "AAPL" in source.get_tickers()

    # Partial sell 4 AAPL @ 250 -> avg_cost stays 200
    cache.update("AAPL", 250.0)
    sell1 = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 4})
    assert sell1.status_code == 200
    pos = sell1.json()["portfolio"]["positions"][0]
    assert pos["quantity"] == 6.0
    assert pos["avg_cost"] == 200.0
    assert sell1.json()["portfolio"]["cash_balance"] == 9000.0

    # Full sell remaining 6 AAPL -> position deleted AND removed from MarketDataSource (not in watchlist)
    sell2 = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 6})
    assert sell2.status_code == 200
    assert sell2.json()["portfolio"]["positions"] == []
    assert sell2.json()["portfolio"]["cash_balance"] == 10500.0
    assert "AAPL" not in source.get_tickers()


async def test_trade_domain_errors_and_validation(client_and_state) -> None:
    client, cache, _ = client_and_state

    # Insufficient cash
    r_cash = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 100})
    assert r_cash.status_code == 400
    assert "Insufficient cash" in r_cash.json()["detail"]

    # Sell without position
    r_sell = await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 1})
    assert r_sell.status_code == 400

    # Price unavailable
    r_noprice = await client.post("/api/portfolio/trade", json={"ticker": "ZZZZ", "side": "buy", "quantity": 1})
    assert r_noprice.status_code == 400
    assert "Price not yet available for ZZZZ" in r_noprice.json()["detail"]

    # Missing price fallback to avg_cost in GET /api/portfolio
    await client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5})
    cache.remove("AAPL")
    p = await client.get("/api/portfolio")
    assert p.status_code == 200
    assert p.json()["positions"][0]["current_price"] == 200.0

    # Invalid ticker / quantity -> 422
    for payload in [
        {"ticker": "123", "side": "buy", "quantity": 1},
        {"ticker": "TOOLONG", "side": "buy", "quantity": 1},
        {"ticker": "AAPL", "side": "buy", "quantity": 0},
        {"ticker": "AAPL", "side": "buy", "quantity": -5},
    ]:
        r = await client.post("/api/portfolio/trade", json=payload)
        assert r.status_code == 422


async def test_fractional_shares_and_sell_more_than_held(client_and_state) -> None:
    client, _, _ = client_and_state

    # Buy fractional shares: 2.5 GOOGL @ 150 = $375
    r_buy = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "GOOGL", "side": "buy", "quantity": 2.5},
    )
    assert r_buy.status_code == 200
    assert r_buy.json()["portfolio"]["cash_balance"] == 9625.0
    assert r_buy.json()["portfolio"]["positions"][0]["quantity"] == 2.5

    # Attempt to sell more than held -> 400
    r_over = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "GOOGL", "side": "sell", "quantity": 3.0},
    )
    assert r_over.status_code == 400
    assert "Insufficient shares" in r_over.json()["detail"]

    # Sell exact fractional shares -> position deleted
    r_sell = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "GOOGL", "side": "sell", "quantity": 2.5},
    )
    assert r_sell.status_code == 200
    assert r_sell.json()["portfolio"]["positions"] == []
    assert r_sell.json()["portfolio"]["cash_balance"] == 10000.0
