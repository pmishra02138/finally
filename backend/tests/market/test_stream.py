"""Tests for the SSE stream router and generator."""

import json

from fastapi import FastAPI

from app.market.cache import PriceCache
from app.market.stream import _generate_events, create_stream_router


class _Req:
    client = None

    def __init__(self, disconnect_after: int):
        self._n = 0
        self._after = disconnect_after

    async def is_disconnected(self) -> bool:
        self._n += 1
        return self._n > self._after


async def _collect(cache, polls, mutate=None):
    out = []
    req = _Req(polls)
    gen = _generate_events(cache, req, interval=0)
    async for chunk in gen:
        out.append(chunk)
        if mutate and len(out) == 2:
            mutate()
    return out


def test_fresh_router_per_call():
    r1 = create_stream_router(PriceCache())
    r2 = create_stream_router(PriceCache())
    assert r1 is not r2
    assert len(r1.routes) == 1 and len(r2.routes) == 1
    app = FastAPI()
    app.include_router(r1)
    app2 = FastAPI()
    app2.include_router(r2)


async def test_retry_and_prices():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    out = await _collect(cache, 1)
    assert out[0] == "retry: 1000\n\n"
    assert json.loads(out[1][len("data: "):])["AAPL"]["price"] == 190.0


async def test_empty_cache_emits_empty_object():
    out = await _collect(PriceCache(), 1)
    assert out[1] == "data: {}\n\n"


async def test_removal_pushes_update():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    out = await _collect(cache, 3, mutate=lambda: cache.remove("AAPL"))
    assert out[-1] == "data: {}\n\n"
