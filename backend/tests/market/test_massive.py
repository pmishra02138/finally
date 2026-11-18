"""Tests for MassiveDataSource (mocked)."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from massive.exceptions import BadResponse
from massive.rest.models import GroupedDailyAgg, TickerSnapshot

from app.market.cache import PriceCache
from app.market.massive_client import MassiveDataSource, extract_price


def _make_snapshot(ticker: str, price: float, ts_ns: int = 1707580800 * 10**9) -> TickerSnapshot:
    """Build a real TickerSnapshot from Massive JSON keys."""
    return TickerSnapshot.from_dict(
        {"ticker": ticker, "lastTrade": {"p": price, "t": ts_ns}, "updated": ts_ns}
    )


def _bar(ticker: str, close: float, ts_ms: int = 1707580800000) -> GroupedDailyAgg:
    return GroupedDailyAgg.from_dict({"T": ticker, "c": close, "t": ts_ms})


def _source(cache=None, **kw) -> MassiveDataSource:
    src = MassiveDataSource(api_key="k", price_cache=PriceCache() if cache is None else cache, **kw)
    src._client = MagicMock()
    return src


@pytest.mark.asyncio
class TestMassiveDataSource:
    """Unit tests for MassiveDataSource with mocked API."""

    async def test_poll_updates_cache(self):
        """Test that polling updates the cache."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key",
            price_cache=cache,
            poll_interval=60.0,  # Long interval so the loop doesn't auto-poll
        )
        source._tickers = ["AAPL", "GOOGL"]
        source._client = MagicMock()  # Satisfy the _poll_once guard

        mock_snapshots = [
            _make_snapshot("AAPL", 190.50),
            _make_snapshot("GOOGL", 175.25),
        ]

        with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
            await source._poll_once()

        assert cache.get_price("AAPL") == 190.50
        assert cache.get_price("GOOGL") == 175.25

    async def test_api_error_does_not_crash(self):
        """Test that API errors don't crash the poller."""
        cache = PriceCache()
        source = MassiveDataSource(
            api_key="test-key",
            price_cache=cache,
            poll_interval=60.0,
        )
        source._tickers = ["AAPL"]
        source._client = MagicMock()  # Satisfy the _poll_once guard

        with patch.object(source, "_fetch_snapshots", side_effect=Exception("network error")):
            await source._poll_once()  # Should not raise

        assert cache.get_price("AAPL") is None  # No update happened

    async def test_timestamp_nanoseconds_to_seconds(self):
        cache = PriceCache()
        source = _source(cache)
        source._tickers = ["AAPL"]
        with patch.object(source, "_fetch_snapshots", return_value=[_make_snapshot("AAPL", 190.5)]):
            await source._poll_once()
        assert cache.get("AAPL").timestamp == 1707580800.0

    async def test_last_trade_none_falls_back(self):
        cache = PriceCache()
        source = _source(cache)
        source._tickers = ["AAPL"]
        snap = TickerSnapshot.from_dict(
            {"ticker": "AAPL", "min": {"c": 191.0}, "updated": 1707580800 * 10**9}
        )
        with patch.object(source, "_fetch_snapshots", return_value=[snap]):
            await source._poll_once()
        assert cache.get_price("AAPL") == 191.0
        assert cache.get("AAPL").timestamp == 1707580800.0

    async def test_zeroed_day_falls_back_to_prev_close(self):
        snap = TickerSnapshot.from_dict(
            {"ticker": "AAPL", "day": {"c": 0}, "prevDay": {"c": 189.19}}
        )
        price, ts = extract_price(snap)
        assert price == 189.19
        assert ts > 0

    async def test_no_usable_price_skipped(self):
        cache = PriceCache()
        source = _source(cache)
        source._tickers = ["BAD", "AAPL"]
        bad = TickerSnapshot.from_dict({"ticker": "BAD", "day": {"c": 0}})
        with patch.object(
            source, "_fetch_snapshots", return_value=[bad, _make_snapshot("AAPL", 190.5)]
        ):
            await source._poll_once()
        assert cache.get_price("BAD") is None
        assert cache.get_price("AAPL") == 190.5

    async def test_removed_mid_poll_is_discarded(self):
        cache = PriceCache()
        source = _source(cache)
        source._tickers = ["AAPL", "MSFT"]

        def fetch(tickers):
            assert tickers == ["AAPL", "MSFT"]
            source._tickers = ["AAPL"]  # removed while request in flight
            return [_make_snapshot("AAPL", 1.0), _make_snapshot("MSFT", 2.0)]

        with patch.object(source, "_fetch_snapshots", side_effect=fetch):
            await source._poll_once()
        assert cache.get_price("AAPL") == 1.0
        assert cache.get_price("MSFT") is None

    async def test_not_authorized_switches_to_eod(self, caplog):
        cache = PriceCache()
        source = _source(cache)
        source._tickers = ["AAPL"]
        err = BadResponse('{"status": "NOT_AUTHORIZED", "message": "not entitled"}')
        with patch.object(source, "_fetch_snapshots", side_effect=err), patch.object(
            source, "_fetch_eod", return_value=[_bar("AAPL", 188.0), _bar("ZZ", 1.0)]
        ):
            await source._poll_once()
        assert source._mode == "eod"
        assert cache.get_price("AAPL") == 188.0
        assert cache.get("AAPL").timestamp == 1707580800.0
        assert cache.get_price("ZZ") is None
        assert sum("no snapshot access" in r.message for r in caplog.records) == 1

    async def test_other_bad_response_keeps_snapshot_mode(self):
        source = _source()
        source._tickers = ["AAPL"]
        with patch.object(source, "_fetch_snapshots", side_effect=BadResponse("Unknown API Key")):
            await source._poll_once()
        assert source._mode == "snapshot"

    async def test_eod_add_ticker_fills_from_cached_bars(self):
        cache = PriceCache()
        source = _source(cache)
        source._mode = "eod"
        source._eod_bars = {"MSFT": _bar("MSFT", 400.0)}
        await source.add_ticker(" msft ")
        assert cache.get_price("MSFT") == 400.0

    async def test_eod_walks_back_over_empty_days(self):
        source = _source()
        calls = []

        def grouped(date, adjusted):
            calls.append(date)
            return [_bar("AAPL", 1.0)] if len(calls) == 3 else []

        source._client.get_grouped_daily_aggs.side_effect = grouped
        bars = source._fetch_eod()
        assert len(calls) == 3 and len(set(calls)) == 3
        assert bars[0].ticker == "AAPL"

    async def test_eod_gives_up_after_lookback(self):
        source = _source()
        source._client.get_grouped_daily_aggs.return_value = []
        assert source._fetch_eod() == []
        assert source._client.get_grouped_daily_aggs.call_count == source.EOD_MAX_LOOKBACK

    async def test_eod_poll_interval_floor(self):
        source = _source(poll_interval=15.0)
        source._mode = "eod"
        sleeps = []

        async def fake_sleep(t):
            sleeps.append(t)
            raise asyncio.CancelledError

        with patch("app.market.massive_client.asyncio.sleep", fake_sleep):
            with pytest.raises(asyncio.CancelledError):
                await source._poll_loop()
        assert sleeps == [300.0]

    async def test_start_uses_explicit_key_retries_and_normalizes(self):
        source = MassiveDataSource(api_key="secret", price_cache=PriceCache(), poll_interval=60.0)
        with patch("app.market.massive_client.RESTClient") as rc:
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start([" aapl", "AAPL", "msft"])
        rc.assert_called_once_with(api_key="secret", retries=1)
        assert source.get_tickers() == ["AAPL", "MSFT"]
        await source.stop()

    async def test_add_ticker(self):
        """Test adding a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("AAPL")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_uppercase_normalization(self):
        """Test that tickers are normalized to uppercase."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("aapl")
        assert "AAPL" in source.get_tickers()

    async def test_add_ticker_strips_whitespace(self):
        """Test that ticker whitespace is stripped."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.add_ticker("  AAPL  ")
        assert "AAPL" in source.get_tickers()

    async def test_remove_ticker(self):
        """Test removing a ticker."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]
        cache.update("AAPL", 190.00)

        await source.remove_ticker("AAPL")
        assert "AAPL" not in source.get_tickers()
        assert cache.get("AAPL") is None

    async def test_get_tickers(self):
        """Test getting the list of active tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = ["AAPL", "GOOGL"]

        tickers = source.get_tickers()
        assert tickers == ["AAPL", "GOOGL"]

    async def test_empty_tickers_skips_poll(self):
        """Test that polling is skipped when there are no tickers."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)
        source._tickers = []

        # Should not call _fetch_snapshots
        with patch.object(source, "_fetch_snapshots") as mock_fetch:
            await source._poll_once()
            mock_fetch.assert_not_called()

    async def test_stop_is_idempotent(self):
        """Test that stop() can be called multiple times."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache)

        await source.stop()
        await source.stop()  # Should not raise

    async def test_stop_cancels_task(self):
        """Test that stop() cancels the polling task."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=10.0)

        # Mock the client and start
        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=[]):
                await source.start(["AAPL"])

        # Verify task is running
        assert source._task is not None
        assert not source._task.done()

        # Stop and verify task is cancelled
        await source.stop()
        assert source._task is None

    async def test_start_immediate_poll(self):
        """Test that start() does an immediate poll before starting the loop."""
        cache = PriceCache()
        source = MassiveDataSource(api_key="test-key", price_cache=cache, poll_interval=60.0)

        mock_snapshots = [_make_snapshot("AAPL", 190.50)]

        with patch("app.market.massive_client.RESTClient"):
            with patch.object(source, "_fetch_snapshots", return_value=mock_snapshots):
                await source.start(["AAPL"])

        # Cache should have data immediately from the first poll
        assert cache.get_price("AAPL") == 190.50

        await source.stop()
