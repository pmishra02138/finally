"""Massive (Polygon.io) API client for real market data."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta
from typing import Literal

from massive import RESTClient
from massive.exceptions import BadResponse
from massive.rest.models import GroupedDailyAgg, SnapshotMarketType, TickerSnapshot

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _positive(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def extract_price(snap: TickerSnapshot) -> tuple[float, float] | None:
    """Return (price, unix_seconds) from a snapshot, or None if no usable price.

    Price falls back last_trade.price -> min.close -> day.close -> prev_day.close
    (0/None treated as missing). Timestamps are nanoseconds.
    """
    price = (
        _positive(snap.last_trade.price if snap.last_trade else None)
        or _positive(snap.min.close if snap.min else None)
        or _positive(snap.day.close if snap.day else None)
        or _positive(snap.prev_day.close if snap.prev_day else None)
    )
    if price is None:
        return None
    ns = (snap.last_trade.sip_timestamp if snap.last_trade else None) or snap.updated
    ts = ns / 1e9 if ns else time.time()
    return price, ts


class MassiveDataSource(MarketDataSource):
    """MarketDataSource backed by the Massive (Polygon.io) REST API.

    Two strategies, chosen at runtime:
      - snapshot (default, paid plans): one get_snapshot_all() per poll.
      - eod (free plan): if the snapshot call fails with NOT_AUTHORIZED, switch
        permanently to grouped daily closes, polled every max(interval, 300)s.
    """

    EOD_MIN_INTERVAL = 300.0
    EOD_MAX_LOOKBACK = 7

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._mode: Literal["snapshot", "eod"] = "snapshot"
        self._eod_bars: dict[str, GroupedDailyAgg] = {}
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None

    async def start(self, tickers: list[str]) -> None:
        # Explicit key (default reads env at import time); retries=1 because
        # built-in retries also fire on 429 and burn rate-limit budget.
        self._client = RESTClient(api_key=self._api_key, retries=1)
        self._tickers = list(dict.fromkeys(normalize_ticker(t) for t in tickers))

        # Immediate first poll so the cache has data right away (never raises)
        await self._poll_once()

        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(self._tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        bar = self._eod_bars.get(ticker) if self._mode == "eod" else None
        if bar is not None and bar.close:
            self._cache.update(ticker, bar.close, (bar.timestamp or 0) / 1000.0 or None)
        logger.info("Massive: added ticker %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed ticker %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # --- Internal ---

    async def _poll_loop(self) -> None:
        """Poll on interval. First poll already happened in start()."""
        while True:
            if self._mode == "snapshot":
                interval = self._interval
            else:
                interval = max(self._interval, self.EOD_MIN_INTERVAL)
            await asyncio.sleep(interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        """One poll cycle. Never raises."""
        tickers = list(self._tickers)  # copy: add/remove may run during the fetch
        if not tickers or not self._client:
            return

        try:
            if self._mode == "snapshot":
                prices = await self._poll_snapshot(tickers)
            else:
                prices = await self._poll_eod(tickers)
        except BadResponse as e:
            if self._mode == "snapshot" and "NOT_AUTHORIZED" in str(e):
                logger.warning(
                    "Massive plan has no snapshot access; showing end-of-day closes"
                )
                self._mode = "eod"
                return await self._poll_once()
            logger.error("Massive poll failed: %s", e)
            return
        except Exception as e:
            logger.error("Massive poll failed: %s", e)
            return

        current = set(self._tickers)  # drop results for tickers removed mid-poll
        for ticker, (price, ts) in prices.items():
            if ticker in current:
                self._cache.update(ticker=ticker, price=price, timestamp=ts)
        logger.debug("Massive poll (%s): updated %d tickers", self._mode, len(prices))

    async def _poll_snapshot(self, tickers: list[str]) -> dict[str, tuple[float, float]]:
        snapshots = await asyncio.to_thread(self._fetch_snapshots, tickers)
        out: dict[str, tuple[float, float]] = {}
        for snap in snapshots:
            try:
                extracted = extract_price(snap)
            except (AttributeError, TypeError) as e:
                logger.warning("Skipping snapshot for %s: %s", getattr(snap, "ticker", "???"), e)
                continue
            if extracted is not None:
                out[snap.ticker] = extracted
        return out

    async def _poll_eod(self, tickers: list[str]) -> dict[str, tuple[float, float]]:
        bars = await asyncio.to_thread(self._fetch_eod)
        self._eod_bars = {b.ticker: b for b in bars}
        out: dict[str, tuple[float, float]] = {}
        for t in tickers:
            bar = self._eod_bars.get(t)
            if bar is not None and bar.close:
                out[t] = (bar.close, (bar.timestamp or 0) / 1000.0 or time.time())
        return out

    def _fetch_snapshots(self, tickers: list[str]) -> list[TickerSnapshot]:
        """Synchronous call to the Massive REST API. Runs in a thread."""
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=tickers,
        )

    def _fetch_eod(self) -> list[GroupedDailyAgg]:
        """Grouped daily bars for the latest trading day, walking back over gaps."""
        d = date.today()
        for _ in range(self.EOD_MAX_LOOKBACK):
            bars = self._client.get_grouped_daily_aggs(date=d.isoformat(), adjusted=True)
            if bars:
                return list(bars)
            d -= timedelta(days=1)
        return []
