# Massive API Reference (formerly Polygon.io)

Reference for retrieving **real-time / delayed** and **end-of-day** US stock prices for
**multiple tickers** from Massive, as used by FinAlly's `MassiveDataSource`.

> **How this was researched (2026-11-17).** Endpoint behaviour, plan entitlements and the
> data-reset schedule come from Massive's official REST docs (links at the bottom). Python
> method signatures and model field names were read directly from the source of the
> `massive==2.2.0` wheel pinned in `backend/uv.lock` (sha256 verified). Where the docs are
> silent and a value is inferred, this document says so.

---

## 1. Key facts at a glance

| Item | Value |
|---|---|
| Rebrand | Polygon.io became **Massive.com** on 2025-10-30. Existing keys and endpoints keep working. |
| Base URL | `https://api.massive.com` (legacy `https://api.polygon.io` still answers) |
| Python package | `massive` (`uv add massive`). FinAlly pins **2.2.0**. |
| Client | `massive.RESTClient`, which is **synchronous** (urllib3). Call it via `asyncio.to_thread` from async code. |
| Auth | `Authorization: Bearer <KEY>` header (what the client sends) or `?apiKey=<KEY>` query param |
| Ticker case | Path and `tickers=` values are **case-sensitive**. Always send upper case. |
| Free-tier limit | **5 requests / minute** (Stocks Basic). This figure is widely published, including in our PLAN, but it is not stated on the endpoint pages. Exceeding it returns HTTP `429`. |

### Plan entitlements (from the endpoint docs)

| Plan | Snapshot endpoints | Aggregates (prev close, grouped daily, open/close) | Data recency | History |
|---|---|---|---|---|
| **Stocks Basic** (free) | ❌ **not included** | ✅ | **End-of-day** | 2 years |
| Stocks Starter | ✅ | ✅ | 15-minute delayed | 5 years |
| Stocks Developer | ✅ | ✅ | 15-minute delayed | 10 years |
| Stocks Advanced | ✅ | ✅ | **Real-time** | All |
| Stocks Business | ✅ (+ `fmv`) | ✅ | Real-time | All |

> ⚠️ **Design consequence.** A free (Basic) key **cannot call the snapshot endpoint**. The
> request fails with a non-200 "not authorized" response. A free key can only fetch
> **end-of-day** data through the aggregates endpoints. FinAlly must therefore support two
> fetch strategies: **snapshot** on paid plans and **end-of-day grouped daily** on the free
> plan. See §6 and `MARKET_INTERFACE.md`.

---

## 2. Client setup

```python
import os
from massive import RESTClient

# Always pass the key explicitly. RESTClient's default is `api_key=os.getenv("MASSIVE_API_KEY")`
# evaluated when the module is imported, so a key loaded later by python-dotenv is NOT seen.
client = RESTClient(
    api_key=os.environ["MASSIVE_API_KEY"],
    connect_timeout=10.0,  # defaults shown
    read_timeout=10.0,
    retries=3,             # urllib3 retries on 413/429/499/500/502/503/504, backoff 0.1s,0.2s,0.4s…
)
```

Relevant constructor arguments in `massive==2.2.0`: `api_key`, `connect_timeout`,
`read_timeout`, `num_pools`, `retries`, `base`, `pagination`, `verbose`, `trace`.

**Retries and the free tier.** The built-in retry also fires on `429`. Each retry is
another request against the 5/min budget, and the backoff (0.1 s → 1.6 s) is far shorter
than the one-minute window. For a free key, construct the client with `retries=0` or
`retries=1` and let FinAlly's poll interval do the pacing.

### Errors

| Exception (`massive.exceptions`) | When |
|---|---|
| `AuthError` | Raised by the constructor when `api_key is None` |
| `BadResponse` | Any non-200 response, after retries. `str(e)` is the **raw response body** (JSON text). The HTTP status code is *not* attached. |

Typical bodies. These are illustrative, in the long-standing Polygon format. The exact text
was not verified against a live key, so match on the `status` / keyword, not on the full message:

```json
{"status": "ERROR", "request_id": "…", "error": "Unknown API Key"}                                  // 401
{"status": "NOT_AUTHORIZED", "request_id": "…", "message": "You are not entitled to this data…"}  // 403, plan lacks endpoint
{"status": "ERROR", "request_id": "…", "error": "You've exceeded the maximum requests per minute…"} // 429
```

Because there is no status code, classify by substring:

```python
from massive.exceptions import BadResponse

def is_not_entitled(exc: Exception) -> bool:
    return isinstance(exc, BadResponse) and "NOT_AUTHORIZED" in str(exc)
```

Other client behaviour worth knowing:
- If the response JSON lacks the expected `result_key` (e.g. no `results` on a market holiday),
  the client returns **`[]`** instead of raising.
- A JSON decode error is logged and returns `[]`.

---

## 3. Real-time / delayed prices: snapshots (paid plans)

### 3.1 Full Market Snapshot, multiple tickers in one call ★ primary endpoint

`GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,NVDA&include_otc=false`

- `tickers`: comma-separated, case-sensitive. Omit it to get the whole market (10,000+ tickers).
  The docs state no maximum, but keep requests to the tracked set (tens of tickers).
- `include_otc`: default `false`.
- One request covers every tracked ticker, which is what makes polling affordable.
- **Reset:** snapshot data is cleared daily at **3:30 AM ET** and repopulates from ~4:00 AM ET as
  exchanges report. Between 3:30 and the first trade of the day, `day` values can be zero or
  empty. Fall back to `prev_day.close` (see §3.3).
- Unknown or invalid tickers are simply absent from the response. No error is raised.

```python
from massive import RESTClient
from massive.rest.models import SnapshotMarketType

client = RESTClient(api_key=API_KEY)

snapshots = client.get_snapshot_all(
    market_type=SnapshotMarketType.STOCKS,   # or "stocks"
    tickers=["AAPL", "MSFT", "NVDA"],        # list is joined with "," by the client
    include_otc=False,
)  # -> list[TickerSnapshot]

for s in snapshots:
    print(s.ticker, s.last_trade.price if s.last_trade else None,
          s.todays_change_percent, s.prev_day.close if s.prev_day else None)
```

**Raw JSON (abridged, one element of `tickers`):**

```json
{
  "ticker": "AAPL",
  "todaysChange": 1.21,
  "todaysChangePerc": 0.64,
  "updated": 1605192894630916600,
  "day":     {"o": 188.1, "h": 191.0, "l": 187.9, "c": 190.4, "v": 51234567, "vw": 189.7},
  "prevDay": {"o": 187.0, "h": 189.6, "l": 186.5, "c": 189.19, "v": 48000000, "vw": 188.2},
  "min":     {"t": 1684428600000, "o": 190.3, "h": 190.5, "l": 190.2, "c": 190.4, "v": 120000, "vw": 190.35, "av": 51234567, "n": 900},
  "lastTrade": {"p": 190.40, "s": 100, "t": 1605192894630916600, "x": 4, "i": "…", "c": [14, 41]},
  "lastQuote": {"p": 190.39, "s": 2, "P": 190.41, "S": 3, "t": 1605192959994246100}
}
```

**Python model (`massive.rest.models.TickerSnapshot`): the attribute names you actually get:**

| Attribute | Type | JSON key | Notes |
|---|---|---|---|
| `ticker` | `str` | `ticker` | |
| `last_trade` | `LastTrade \| None` | `lastTrade` | Present **only if your plan includes trades** |
| `last_quote` | `LastQuote \| None` | `lastQuote` | Present **only if your plan includes quotes** |
| `day` | `Agg \| None` | `day` | Today's session: `open, high, low, close, volume, vwap` |
| `prev_day` | `Agg \| None` | `prevDay` | Previous session. `prev_day.close` is the **previous close**. |
| `min` | `MinuteSnapshot \| None` | `min` | Latest minute bar: `open, high, low, close, volume, vwap, accumulated_volume, timestamp (ms)` |
| `todays_change` | `float \| None` | `todaysChange` | vs previous close |
| `todays_change_percent` | `float \| None` | `todaysChangePerc` | vs previous close |
| `updated` | `int \| None` | `updated` | Last update, **nanoseconds** (inferred from 19-digit samples) |
| `fair_market_value` | `float \| None` | `fmv` | Business plan only |

`LastTrade` fields: `price`, `size`, `exchange`, `conditions`, `id`, `tape`,
**`sip_timestamp`** (ns), `participant_timestamp` (ns), `trf_timestamp`, `sequence_number`.

`LastQuote` fields: `bid_price`, `bid_size`, `ask_price`, `ask_size`, `sip_timestamp` (ns), ….

> ⚠️ **Common mistakes, some of which are in the archived doc and in the current code:**
> - There is **no `last_trade.timestamp`** attribute. It is `last_trade.sip_timestamp`, in
>   **nanoseconds** (divide by `1e9`, not `1e3`).
> - `day` is an `Agg`. It has **no** `previous_close` and **no** `change_percent`. Use
>   `prev_day.close` and `todays_change_percent`.
> - `LastQuote` uses `bid_price`/`ask_price` (the standalone last-quote endpoint's JSON uses `p`/`P`).
>
> Unit tests that build snapshots with `MagicMock` will not catch these, because a
> `MagicMock` accepts any attribute. Build test fixtures with
> `TickerSnapshot.from_dict({...})` using real JSON keys.

### 3.2 Single Ticker Snapshot

`GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}`. Same object, returned
under `"ticker"` instead of a `"tickers"` array. Same plan requirement. Not needed for polling.

```python
snap = client.get_snapshot_ticker(SnapshotMarketType.STOCKS, "AAPL")  # -> TickerSnapshot
```

### 3.3 Robust price extraction from a snapshot

```python
import time
from massive.rest.models import TickerSnapshot

def _positive(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and x > 0 else None

def extract_price(s: TickerSnapshot) -> tuple[float, float] | None:
    """Return (price, unix_seconds) or None if the snapshot has no usable price."""
    price = (
        _positive(s.last_trade.price if s.last_trade else None)   # best: last trade
        or _positive(s.min.close if s.min else None)              # latest minute bar
        or _positive(s.day.close if s.day else None)              # today's session
        or _positive(s.prev_day.close if s.prev_day else None)    # after 3:30 AM reset / pre-market
    )
    if price is None:
        return None
    ns = (s.last_trade.sip_timestamp if s.last_trade else None) or s.updated
    ts = ns / 1e9 if ns else time.time()
    return price, ts
```

---

## 4. End-of-day prices (all plans, including free)

### 4.1 Daily Market Summary (grouped daily): all tickers, one call ★ free-tier primary

`GET /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true&include_otc=false`

Returns one OHLCV bar per ticker for the **entire US market** on `date` (`YYYY-MM-DD`). This
is the only way to get EOD prices for many tickers in a single call, so it is the right
endpoint under a 5/min limit. Filter the result client-side to the tracked set.

```python
from datetime import date, timedelta

bars = client.get_grouped_daily_aggs(
    date="2026-11-16",     # str or datetime.date
    adjusted=True,
    include_otc=False,
)  # -> list[GroupedDailyAgg]; [] on weekends/holidays/not-yet-published

wanted = {"AAPL", "MSFT", "NVDA"}
closes = {b.ticker: b.close for b in bars if b.ticker in wanted}
```

`GroupedDailyAgg` fields: `ticker, open, high, low, close, volume, vwap, timestamp (ms, end
of window), transactions, otc`.

On a weekend or holiday, or before that day's bars are published, the result is `[]`. Walk
back to the most recent day that has data:

```python
def latest_grouped_daily(client, max_lookback: int = 7):
    d = date.today()
    for _ in range(max_lookback):
        bars = client.get_grouped_daily_aggs(date=d.isoformat(), adjusted=True)
        if bars:
            return d, bars
        d -= timedelta(days=1)
    return None, []
```

Each step back costs one request. Cache the date that worked and re-check at most every
few minutes. EOD data changes once a day.

To get "previous close" for change calculations, fetch the trading day **before** the
latest one. That is a second call, made once at start-up, not on every poll.

### 4.2 Previous Day Bar: per ticker

`GET /v2/aggs/ticker/{stocksTicker}/prev?adjusted=true`, all plans.

```python
res = client.get_previous_close_agg("AAPL")   # -> list[PreviousCloseAgg] (despite the type hint)
prev = res[0] if res else None
print(prev.close, prev.open, prev.high, prev.low, prev.volume, prev.timestamp)  # timestamp: ms
```

One request **per ticker**. With 10 tickers on the free tier that takes 2 minutes of quota,
so use grouped daily instead for the watchlist. This endpoint is fine for a one-off lookup
of a single newly added ticker.

### 4.3 Daily Ticker Summary (open/close): per ticker, specific date

`GET /v1/open-close/{stocksTicker}/{date}`, all plans. Includes pre-market and after-hours.

```python
oc = client.get_daily_open_close_agg("AAPL", "2026-11-16")   # -> DailyOpenCloseAgg
print(oc.open, oc.high, oc.low, oc.close, oc.pre_market, oc.after_hours, oc.volume)
```

### 4.4 Historical bars (custom range)

`GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}`. Not used today. It
would be useful for back-filling the main chart.

```python
bars = client.get_aggs("AAPL", 1, "day", "2026-10-01", "2026-11-16", adjusted=True, sort="asc")
# or the paginating iterator:
for a in client.list_aggs("AAPL", 5, "minute", "2026-11-16", "2026-11-16", limit=50000):
    print(a.timestamp, a.close)   # Agg: open, high, low, close, volume, vwap, timestamp (ms)
```

---

## 5. Other single-ticker endpoints (reference only)

| Method | Endpoint | Returns |
|---|---|---|
| `client.get_last_trade("AAPL")` | `/v2/last/trade/{ticker}` | `LastTrade` (`price`, `size`, `sip_timestamp` ns) |
| `client.get_last_quote("AAPL")` | `/v2/last/nbbo/{ticker}` | `LastQuote` (`bid_price`, `ask_price`, …) |

Both are per-ticker and need a trades/quotes entitlement. FinAlly does not use them.

WebSockets (`massive.WebSocketClient`) provide true streaming on real-time plans. FinAlly
deliberately polls REST instead (PLAN §6).

---

## 6. How FinAlly uses the API

| Plan | Endpoint per poll | Calls / poll | Suggested interval | What the user sees |
|---|---|---|---|---|
| Free (Basic) | Grouped daily (§4.1), latest trading day | 1 | 60 s or more (data changes daily) | Last close, static during the day |
| Starter / Developer | Full snapshot (§3.1) | 1 | 15 s default (PLAN), 2–5 s possible | 15-min delayed prices |
| Advanced / Business | Full snapshot (§3.1) | 1 | 15 s default, 2–5 s possible | Real-time prices |

The plan is not known in advance, so detect it at runtime. Try the snapshot first. If it
fails with `NOT_AUTHORIZED`, switch permanently to the grouped-daily strategy and log a
clear message once:

```python
import asyncio, logging
from massive import RESTClient
from massive.exceptions import BadResponse
from massive.rest.models import SnapshotMarketType

log = logging.getLogger(__name__)

async def fetch_prices(client: RESTClient, tickers: list[str], state: dict) -> dict[str, tuple[float, float]]:
    """Return {ticker: (price, unix_seconds)} using snapshot, or EOD if not entitled."""
    if state.get("mode", "snapshot") == "snapshot":
        try:
            snaps = await asyncio.to_thread(
                client.get_snapshot_all, SnapshotMarketType.STOCKS, tickers)
            out = {}
            for s in snaps:
                p = extract_price(s)
                if p:
                    out[s.ticker] = p
            return out
        except BadResponse as e:
            if "NOT_AUTHORIZED" not in str(e):
                raise
            log.warning("Massive plan has no snapshot access; using end-of-day prices")
            state["mode"] = "eod"

    day, bars = await asyncio.to_thread(latest_grouped_daily, client)
    wanted = set(tickers)
    return {b.ticker: (b.close, b.timestamp / 1000) for b in bars
            if b.ticker in wanted and b.close}
```

The production version of this logic, with its interface, intervals and tests, is specified
in `MARKET_INTERFACE.md` §5.

---

## 7. Gotchas checklist

1. Pass `api_key=` explicitly. Don't rely on the import-time env default.
2. `RESTClient` is synchronous. Use `asyncio.to_thread`, never call it directly in the event loop.
3. Free key means **no snapshot**. Handle `NOT_AUTHORIZED` and fall back to grouped daily.
4. Timestamps: `lastTrade.t`, `lastQuote.t` and `updated` are **ns**. Aggregate `t` and `min.t` are **ms**.
5. `last_trade` / `last_quote` can be `None` depending on plan. Fall back through `min` → `day` → `prev_day`.
6. Snapshot `day` is zeroed after the 3:30 AM ET reset. Treat `0` as missing.
7. Tickers are case-sensitive. Unknown tickers are silently omitted, not errors.
8. Grouped daily returns `[]` on non-trading days. Walk back by date.
9. `BadResponse` carries only the body text. Classify errors by its `status`/`error` content.
10. Built-in retries consume rate-limit budget. Lower `retries` on the free tier.
11. Test with `TickerSnapshot.from_dict(real_json)`, not `MagicMock`.

## Sources

- [Full Market Snapshot](https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot)
- [Single Ticker Snapshot](https://massive.com/docs/rest/stocks/snapshots/single-ticker-snapshot)
- [Previous Day Bar](https://massive.com/docs/rest/stocks/aggregates/previous-day-bar)
- [Daily Market Summary (grouped daily)](https://massive.com/docs/rest/stocks/aggregates/daily-market-summary)
- [Daily Ticker Summary (open/close)](https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary)
- [REST Quickstart (auth)](https://massive.com/docs/rest/quickstart)
- [Docs index](https://massive.com/docs/rest/llms.txt)
- [Pricing](https://massive.com/pricing)
- `massive==2.2.0` source: `massive/rest/{__init__,base,snapshot,aggs,trades}.py`, `massive/rest/models/{snapshot,aggs,trades,quotes}.py`
