"""Unit and API tests for watchlist CRUD and MarketDataSource sync."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client_and_app(tmp_path: Path):
    app = create_app(db_path=tmp_path / "watchlist.db", snapshot_interval=3600.0)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def test_watchlist_crud_and_validation(client_and_app) -> None:
    client, app = client_and_app

    # Initial 10 tickers with prices from simulator
    r_get = await client.get("/api/watchlist")
    assert r_get.status_code == 200
    tickers = [t["ticker"] for t in r_get.json()["tickers"]]
    assert len(tickers) == 10
    assert "AAPL" in tickers
    assert r_get.json()["tickers"][0]["price"] is not None

    # Add new ticker (normalized from lowercase + whitespace)
    r_add = await client.post("/api/watchlist", json={"ticker": " pypl "})
    assert r_add.status_code == 201
    assert r_add.json()["ticker"] == "PYPL"
    assert "PYPL" in app.state.market_data_source.get_tickers()

    # Duplicate -> 409
    r_dup = await client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert r_dup.status_code == 409

    # Invalid ticker -> 422
    r_inv = await client.post("/api/watchlist", json={"ticker": "BAD123"})
    assert r_inv.status_code == 422

    # Delete ticker (normalized from lowercase)
    r_del = await client.delete("/api/watchlist/pypl")
    assert r_del.status_code == 200
    assert r_del.json() == {"ticker": "PYPL", "removed": True}
    assert "PYPL" not in app.state.market_data_source.get_tickers()

    # Delete missing -> 404
    r_404 = await client.delete("/api/watchlist/PYPL")
    assert r_404.status_code == 404

    # Delete invalid ticker -> 422
    r_del_inv = await client.delete("/api/watchlist/12345")
    assert r_del_inv.status_code == 422
