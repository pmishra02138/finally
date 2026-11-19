"""Tests for health endpoint, OpenAPI schema, APP_PASSWORD middleware, and snapshot loop."""

from __future__ import annotations

import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_and_openapi_contract(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "health.db", snapshot_interval=3600.0)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_health = await client.get("/api/health")
            assert r_health.status_code == 200
            body = r_health.json()
            assert body["status"] == "ok"
            assert body["tracked_tickers"] == 10

            r_openapi = await client.get("/openapi.json")
            assert r_openapi.status_code == 200
            paths = r_openapi.json()["paths"]
            expected_paths = {
                "/api/health",
                "/api/stream/prices",
                "/api/portfolio",
                "/api/portfolio/trade",
                "/api/portfolio/history",
                "/api/watchlist",
                "/api/watchlist/{ticker}",
                "/api/chat",
                "/api/chat/history",
            }
            assert expected_paths.issubset(set(paths.keys()))


async def test_app_password_middleware_and_static_mount(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APP_PASSWORD", "s3cr3t-pass")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>FinAlly UI</h1>", encoding="utf-8")

    app = create_app(
        db_path=tmp_path / "auth.db",
        snapshot_interval=3600.0,
        static_dir=static_dir,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Static frontend at / is NOT blocked by APP_PASSWORD
            r_root = await client.get("/")
            assert r_root.status_code == 200
            assert "FinAlly UI" in r_root.text

            # /api/health is exempt
            assert (await client.get("/api/health")).status_code == 200

            # Missing or wrong header -> 401
            assert (await client.get("/api/portfolio")).status_code == 401
            assert (
                await client.get("/api/portfolio", headers={"X-App-Password": "wrong"})
            ).status_code == 401

            # Correct header -> 200
            assert (
                await client.get("/api/portfolio", headers={"X-App-Password": "s3cr3t-pass"})
            ).status_code == 200

            # /api/stream/prices rejects missing key and accepts ?key=
            assert (await client.get("/api/stream/prices")).status_code == 401
            assert (await client.get("/api/stream/prices?key=wrong")).status_code == 401

            async def _one_event(_cache, _req):
                yield "retry: 1000\n\n"

            monkeypatch.setattr("app.market.stream._generate_events", _one_event)
            r_sse = await client.get("/api/stream/prices?key=s3cr3t-pass")
            assert r_sse.status_code == 200
            assert "retry: 1000" in r_sse.text


async def test_periodic_snapshot_task(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "snap.db", snapshot_interval=0.1)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.28)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            hist = await client.get("/api/portfolio/history")
            assert hist.status_code == 200
            assert len(hist.json()) >= 3
