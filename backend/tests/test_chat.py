"""Unit and API tests for LLM chat (mock mode, Cerebras acompletion, retries, rate limiting)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.schemas import LLMResponse
from app.services.chat import EXTRA_BODY, FALLBACK_MESSAGE, MODEL


def _make_completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture
async def mock_chat_client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    app = create_app(db_path=tmp_path / "chat_mock.db", snapshot_interval=3600.0)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app


async def test_mock_mode_buy_sell_watchlist_and_history(mock_chat_client) -> None:
    client, _ = mock_chat_client

    # Buy trade
    r_buy = await client.post("/api/chat", json={"message": "buy 2 aapl"})
    assert r_buy.status_code == 200
    body = r_buy.json()
    assert body["role"] == "assistant"
    assert len(body["actions"]) == 1
    assert body["actions"][0]["type"] == "trade"
    assert body["actions"][0]["ticker"] == "AAPL"
    assert body["actions"][0]["side"] == "buy"
    assert body["actions"][0]["status"] == "executed"
    assert body["actions"][0]["price"] > 0

    # Sell trade
    r_sell = await client.post("/api/chat", json={"message": "sell 1 AAPL"})
    assert r_sell.status_code == 200
    assert r_sell.json()["actions"][0]["status"] == "executed"

    # Watch & unwatch
    r_watch = await client.post("/api/chat", json={"message": "watch PYPL"})
    assert r_watch.status_code == 200
    assert r_watch.json()["actions"][0] == {
        "type": "watchlist",
        "ticker": "PYPL",
        "side": None,
        "quantity": None,
        "price": None,
        "action": "add",
        "status": "executed",
        "error": None,
    }

    r_unwatch = await client.post("/api/chat", json={"message": "remove PYPL"})
    assert r_unwatch.status_code == 200
    assert r_unwatch.json()["actions"][0]["status"] == "executed"

    # General question -> portfolio summary
    r_info = await client.post("/api/chat", json={"message": "How is my portfolio doing?"})
    assert r_info.status_code == 200
    assert "cash" in r_info.json()["content"].lower()
    assert r_info.json()["actions"] == []

    # Failed trade (insufficient cash) returns HTTP 200 with failed action badge
    r_fail = await client.post("/api/chat", json={"message": "buy 99999 AAPL"})
    assert r_fail.status_code == 200
    assert r_fail.json()["actions"][0]["status"] == "failed"
    assert "Insufficient cash" in r_fail.json()["actions"][0]["error"]

    # History persists all user + assistant turns in order
    hist = await client.get("/api/chat/history")
    assert hist.status_code == 200
    msgs = hist.json()["messages"]
    assert len(msgs) == 12
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


async def test_real_llm_acompletion_retry_and_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MOCK", "false")
    app = create_app(db_path=tmp_path / "chat_real.db", snapshot_interval=3600.0)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            valid_json = LLMResponse(
                message="Executed your buy order.",
                trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1.0}],
                watchlist_changes=[],
            ).model_dump_json()

            # 1st attempt raises, 2nd succeeds
            mock_acomp = AsyncMock(side_effect=[RuntimeError("transient"), _make_completion(valid_json)])
            with patch("app.services.chat.litellm.acompletion", mock_acomp):
                resp = await client.post("/api/chat", json={"message": "Buy 1 AAPL"})

            assert resp.status_code == 200
            assert resp.json()["content"] == "Executed your buy order."
            assert resp.json()["actions"][0]["status"] == "executed"
            assert mock_acomp.call_count == 2
            kwargs = mock_acomp.call_args.kwargs
            assert kwargs["model"] == MODEL
            assert kwargs["response_format"] is LLMResponse
            assert kwargs["reasoning_effort"] == "low"
            assert kwargs["extra_body"] == EXTRA_BODY

            # Both attempts fail -> HTTP 200 fallback, persisted
            mock_fail = AsyncMock(side_effect=[_make_completion(""), ValueError("still bad")])
            with patch("app.services.chat.litellm.acompletion", mock_fail):
                resp_fb = await client.post("/api/chat", json={"message": "Analyze risk"})

            assert resp_fb.status_code == 200
            assert resp_fb.json()["content"] == FALLBACK_MESSAGE
            assert resp_fb.json()["actions"] == []

            # LLM returns invalid trade + invalid watchlist + duplicate/missing watchlist -> all recorded as failed
            bad_actions_json = LLMResponse(
                message="Trying several actions.",
                trades=[{"ticker": "BAD999", "side": "buy", "quantity": -5.0}],
                watchlist_changes=[
                    {"ticker": "12345", "action": "add"},
                    {"ticker": "AAPL", "action": "add"},
                    {"ticker": "ZZZZ", "action": "remove"},
                ],
            ).model_dump_json()
            mock_bad_actions = AsyncMock(return_value=_make_completion(bad_actions_json))
            with patch("app.services.chat.litellm.acompletion", mock_bad_actions):
                resp_bad = await client.post("/api/chat", json={"message": "Do weird stuff"})

            assert resp_bad.status_code == 200
            actions = resp_bad.json()["actions"]
            assert len(actions) == 4
            assert all(a["status"] == "failed" and a["error"] for a in actions)

            # Empty / whitespace-only chat message -> 422
            r_empty = await client.post("/api/chat", json={"message": "   "})
            assert r_empty.status_code == 422


async def test_event_loop_not_blocked_during_slow_llm_call(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MOCK", "false")
    app = create_app(db_path=tmp_path / "chat_async.db", snapshot_interval=3600.0)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async def slow_acompletion(**_kwargs):
                await asyncio.sleep(0.8)
                return _make_completion(
                    LLMResponse(message="Done", trades=[], watchlist_changes=[]).model_dump_json()
                )

            version_before = app.state.price_cache.version
            with patch("app.services.chat.litellm.acompletion", side_effect=slow_acompletion):
                resp = await client.post("/api/chat", json={"message": "Wait a moment"})
            version_after = app.state.price_cache.version

            assert resp.status_code == 200
            # Simulator ticks every 500ms, so price_cache must advance during the 800ms LLM call
            assert version_after > version_before


async def test_chat_rate_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    app = create_app(
        db_path=tmp_path / "chat_rl.db",
        snapshot_interval=3600.0,
        chat_rate_limit=3,
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(3):
                r = await client.post("/api/chat", json={"message": "status"})
                assert r.status_code == 200
            r4 = await client.post("/api/chat", json={"message": "status"})
            assert r4.status_code == 429
